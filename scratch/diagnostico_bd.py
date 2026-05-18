import sqlite3
import os

db_path = r'c:\HomeCloud\shared\Projetos\investidor\fiia.db'
print(f'Tamanho do banco: {os.path.getsize(db_path)/1024/1024:.1f} MB')
print()

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tabelas = [r[0] for r in cur.fetchall()]

print(f"{'TABELA':<45} {'REGISTROS':>10}")
print('-' * 57)

vazias = []
com_dados = []

for t in tabelas:
    try:
        cur.execute(f"SELECT COUNT(*) FROM [{t}]")
        count = cur.fetchone()[0]
        if count == 0:
            vazias.append(t)
            print(f"{t:<45} {count:>10}  <- VAZIA")
        else:
            com_dados.append((t, count))
            print(f"{t:<45} {count:>10}")
    except Exception as e:
        print(f"{t:<45} ERRO: {e}")

conn.close()

print()
print(f"Total: {len(tabelas)} tabelas | {len(com_dados)} com dados | {len(vazias)} vazias")
