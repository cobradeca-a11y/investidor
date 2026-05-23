@echo off
REM Suite de testes ampla — roda no CMD do Windows sem quebra de linha
pytest teste_seguranca_api.py teste_api_decisoes.py teste_replay_decisao.py teste_exportacao_relatorios.py teste_relatorios_auditaveis.py teste_frontend_explicabilidade.py teste_frontend_payload.py teste_frontend_replay.py teste_observabilidade_performance.py teste_rate_limit.py teste_api_radar_jobs.py -v
