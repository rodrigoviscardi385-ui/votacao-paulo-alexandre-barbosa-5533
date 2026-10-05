import urllib.request
import zipfile
import io
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

CAND_NUM = "5533"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
ELEICAO_ID = "6259"
CARGO_ID = "c0006"

def carregar_municipios_sp():
    url_muns = "https://cdn.tse.jus.br/estatistica/sead/odsele/municipio_tse_ibge/municipio_tse_ibge.zip"
    print("Baixando base de municípios do TSE...")
    req = urllib.request.Request(url_muns, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        zf = zipfile.ZipFile(io.BytesIO(resp.read()))
        with zf.open('municipio_tse_ibge.csv') as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding='latin1'), delimiter=';')
            sp_muns = [
                {
                    'cd_tse': row['CD_MUNICIPIO_TSE'],
                    'nm_mun': row['NM_MUNICIPIO_TSE'],
                    'cd_ibge': row['CD_MUNICIPIO_IBGE'],
                }
                for row in reader if row['SG_UF'] == 'SP'
            ]
    print(f"Total de {len(sp_muns)} municípios carregados para SP.")
    return sp_muns

def buscar_votacao_municipio(mun):
    cod_tse = mun['cd_tse']
    nm_mun = mun['nm_mun']
    cd_ibge = mun['cd_ibge']
    url = f"https://resultados.tse.jus.br/oficial/ele2026/{ELEICAO_ID}/dados/sp/sp{cod_tse}-{CARGO_ID}-e00{ELEICAO_ID}-u.json"
    
    retries = 3
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                
                urnas_apuradas = data.get('s', {}).get('pst', '0,00')
                total_eleitores = data.get('e', {}).get('te', '0')
                comparecimento = data.get('e', {}).get('c', '0')
                votos_validos = data.get('v', {}).get('vv', '0')
                
                votos_cand = 0
                pct_cand = "0,00"
                cand_nome = ""
                cand_situacao = ""
                
                for c in data.get('carg', []):
                    for agr in c.get('agr', []):
                        for par in agr.get('par', []):
                            for cand in par.get('cand', []):
                                if cand.get('n') == CAND_NUM:
                                    votos_cand = int(cand.get('vap', 0))
                                    pct_cand = cand.get('pvap', '0,00')
                                    cand_nome = cand.get('nm', 'PAULO ALEXANDRE BARBOSA')
                                    cand_situacao = cand.get('dvt', 'Válido')
                                    break
                
                return {
                    'codigo_tse': cod_tse,
                    'codigo_ibge': cd_ibge,
                    'municipio': nm_mun,
                    'votos': votos_cand,
                    'percentual_validos': pct_cand,
                    'votos_validos_cidade': votos_validos,
                    'urnas_apuradas_pct': urnas_apuradas,
                    'comparecimento': comparecimento,
                    'total_eleitores': total_eleitores,
                    'status': 'OK'
                }
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(0.5)
            else:
                return {
                    'codigo_tse': cod_tse,
                    'codigo_ibge': cd_ibge,
                    'municipio': nm_mun,
                    'votos': 0,
                    'percentual_validos': '0,00',
                    'votos_validos_cidade': '0',
                    'urnas_apuradas_pct': '0,00',
                    'comparecimento': '0',
                    'total_eleitores': '0',
                    'status': f'Erro: {str(e)}'
                }

def main():
    municipios = carregar_municipios_sp()
    resultados = []
    
    print("Iniciando coleta dos 645 municípios do Estado de SP...")
    start_time = time.time()
    
    # Usar 12 threads para respeitar o limite de 100 req/s do TSE com bastante folga
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(buscar_votacao_municipio, mun): mun for mun in municipios}
        
        concluidos = 0
        total = len(municipios)
        for future in as_completed(futures):
            res = future.result()
            resultados.append(res)
            concluidos += 1
            if concluidos % 50 == 0 or concluidos == total:
                print(f"Progresso: {concluidos}/{total} municípios processados ({(concluidos/total)*100:.1f}%)...")
                
    elapsed = time.time() - start_time
    print(f"Coleta finalizada em {elapsed:.2f} segundos!")
    
    # Ordenar por votos decrescente
    resultados.sort(key=lambda x: x['votos'], reverse=True)
    
    # Salvar em CSV
    csv_file = "votacao_paulo_alexandre_barbosa_5533_sp.csv"
    with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
        fieldnames = [
            'codigo_tse', 'codigo_ibge', 'municipio', 'votos',
            'percentual_validos', 'votos_validos_cidade', 'urnas_apuradas_pct',
            'comparecimento', 'total_eleitores', 'status'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in resultados:
            writer.writerow(r)
            
    # Salvar em JSON
    json_file = "votacao_paulo_alexandre_barbosa_5533_sp.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
        
    total_votos = sum(r['votos'] for r in resultados)
    municipios_com_votos = [r for r in resultados if r['votos'] > 0]
    
    print("\n" + "="*60)
    print(f"RESUMO DA VOTAÇÃO - PAULO ALEXANDRE BARBOSA (5533)")
    print(f"Total de Votos no Estado de SP: {total_votos:,}".replace(',', '.'))
    print(f"Municípios com Votação Registrada: {len(municipios_com_votos)} de {len(resultados)}")
    print("="*60)
    print("\nTOP 20 CIDADES COM MAIOR VOTAÇÃO:")
    for idx, r in enumerate(resultados[:20], 1):
        print(f"{idx:2d}. {r['municipio']:<30} : {r['votos']:>7,} votos ({r['percentual_validos']}%)".replace(',', '.'))
        
    print(f"\nArquivos gerados com sucesso:\n- {csv_file}\n- {json_file}")

if __name__ == '__main__':
    main()
