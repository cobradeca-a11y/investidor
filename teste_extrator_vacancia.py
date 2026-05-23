"""
Teste do extrator de taxa de ocupação/vacância de FNET
Estratégia:
  1. Tenta pymupdf com PDF real de FNET
  2. Se falhar, tenta CSV da CVM
  3. Se falhar, tenta XML
"""

import io
import re
import requests
import tempfile
import pandas as pd
from pathlib import Path

# ── Teste 1: PyMuPDF com PDF real ──────────────────────────────────

def teste_pymupdf_fnet():
    """Tenta baixar um informe mensal real e extrair vacância com pymupdf"""
    print("\n[TESTE 1] PyMuPDF - Extracting from FNET PDF...")
    
    try:
        import fitz
        print("✓ PyMuPDF importado com sucesso")
        
        # Tenta buscar um PDF de exemplo da tabela mestre local
        from coleta import tabela_mestre_fiis
        
        # Pega um FII ativo
        fiis = tabela_mestre_fiis.listar_fundos_ativos()
        if not fiis:
            print("⚠ Nenhum FII ativo na tabela mestre. Tentando CSV da CVM...")
            return False
            
        fii_teste = fiis[0]
        ticker = fii_teste.get("ticker") or fii_teste.get("nome_fundo")
        cnpj = fii_teste.get("cnpj_fundo")
        
        print(f"  Testando com: {ticker} ({cnpj})")
        
        # Tenta buscar via FNET
        from coleta.relatorio_fnet import obter_relatorio
        
        texto_relatorio = obter_relatorio(ticker)
        if not texto_relatorio:
            print("⚠ Relatório FNET não disponível localmente. Pulando para CSV...")
            return False
            
        print(f"  Relatório obtido ({len(texto_relatorio)} chars)")
        
        # Busca por keywords de ocupação
        palavras_chave = [
            "Ocupação", "Taxa de Ocupação", "Taxa de Ocupação da ABL",
            "Vacância", "Ocupada", "ABL Ocupada", "Ocupação Física"
        ]
        
        linhas = texto_relatorio.split('\n')
        encontrados = []
        
        for i, linha in enumerate(linhas):
            for chave in palavras_chave:
                if chave.lower() in linha.lower():
                    # Extrai a linha e as próximas 2 (para capturar valores numéricos)
                    contexto = linha.strip()
                    if i+1 < len(linhas):
                        contexto += " " + linhas[i+1].strip()
                    if i+2 < len(linhas):
                        contexto += " " + linhas[i+2].strip()
                    encontrados.append(contexto)
                    break
        
        if encontrados:
            print(f"✓ Encontrados {len(encontrados)} resultado(s):")
            for res in encontrados[:3]:  # Mostra os 3 primeiros
                print(f"    {res[:100]}...")
            return True
        else:
            print("⚠ Nenhuma taxa de ocupação encontrada no texto extraído")
            return False
            
    except ImportError as e:
        print(f"✗ PyMuPDF não disponível: {e}")
        return False
    except Exception as e:
        print(f"✗ Erro ao testar PyMuPDF: {e}")
        return False


# ── Teste 2: CSV da CVM ────────────────────────────────────────────

def teste_csv_cvm():
    """Tenta baixar e processar CSV oficial da CVM com dados de ocupação"""
    print("\n[TESTE 2] CSV oficial da CVM...")
    
    try:
        # URL do CSV consolidado da CVM (2026)
        url = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2026.zip"
        
        print(f"  Baixando: {url[:60]}...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        print(f"  ZIP baixado ({len(response.content)} bytes)")
        
        # Tenta ler o CSV do ZIP
        df = pd.read_csv(
            io.BytesIO(response.content),
            sep=";",
            compression="zip",
            encoding="ISO-8859-1",
            nrows=5  # Apenas 5 linhas para teste
        )
        
        print(f"✓ CSV carregado com sucesso")
        print(f"  Colunas: {len(df.columns)}")
        print(f"  Primeiras colunas: {list(df.columns[:5])}")
        
        # Busca por colunas de ocupação
        colunas_ocupacao = [col for col in df.columns 
                           if 'ocupacao' in col.lower() or 'vacancia' in col.lower() or 
                              'abl' in col.lower() or 'taxa' in col.lower()]
        
        if colunas_ocupacao:
            print(f"✓ Colunas relevantes encontradas: {colunas_ocupacao[:5]}")
            return True
        else:
            print("⚠ Nenhuma coluna de ocupação encontrada no CSV")
            print(f"  Amostra de colunas: {list(df.columns[:10])}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Erro ao baixar CSV da CVM: {e}")
        return False
    except Exception as e:
        print(f"✗ Erro ao processar CSV: {e}")
        return False


# ── Teste 3: XML do Fundos.NET ──────────────────────────────────────

def teste_xml_fnet():
    """Tenta buscar e processar XML nativo do Fundos.NET"""
    print("\n[TESTE 3] XML do Fundos.NET...")
    
    try:
        from coleta import cvm_fnet_documentos
        
        # Lista documentos disponíveis
        docs = cvm_fnet_documentos.listar_pendentes(limite=1)
        
        if not docs:
            print("⚠ Nenhum documento FNET disponível localmente")
            return False
        
        doc = docs[0]
        print(f"  Documento: {doc.get('titulo', 'sem título')}")
        
        # Tenta extrair dados estruturados
        print("⚠ XML extraction ainda não implementado (requer schema CVM)")
        return False
        
    except Exception as e:
        print(f"✗ Erro ao acessar XML: {e}")
        return False


# ── Main ────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("TESTE DE EXTRAÇÃO DE TAXA DE OCUPAÇÃO / VACÂNCIA")
    print("=" * 70)
    
    resultados = {
        "PyMuPDF (PDF)": teste_pymupdf_fnet(),
        "CSV da CVM": teste_csv_cvm(),
        "XML Fundos.NET": teste_xml_fnet(),
    }
    
    print("\n" + "=" * 70)
    print("RESUMO DOS TESTES")
    print("=" * 70)
    
    for metodo, resultado in resultados.items():
        status = "✓ OK" if resultado else "✗ FALHOU"
        print(f"{metodo:.<50} {status}")
    
    # Recomendação
    metodos_ok = [m for m, r in resultados.items() if r]
    
    if metodos_ok:
        print(f"\n✓ Recomendação: Use {metodos_ok[0]} para produção")
    else:
        print("\n✗ Nenhum método funcionou. Verifique conectividade e schemas.")


if __name__ == "__main__":
    main()
