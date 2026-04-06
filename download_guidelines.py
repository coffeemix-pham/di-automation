import requests
import os

def download_file(url, filename, user_agent='Mozilla/5.0'):
    headers = {'User-Agent': user_agent}
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Successfully downloaded: {filename}")
    except Exception as e:
        print(f"Failed to download {filename}: {e}")

if __name__ == "__main__":
    kb_dir = "knowledge_base"
    os.makedirs(kb_dir, exist_ok=True)
    
    urls = {
        "fda_di_2018.pdf": "https://www.fda.gov/media/119267/download",
        "who_di_2021.pdf": "https://cdn.who.int/media/docs/default-source/medicines/norms-and-standards/guidelines/inspections/trs1033-annex4-guideline-on-data-integrity.pdf?sfvrsn=6218a4e6_4&download=true",
        "mfds_di_2020.pdf": "https://www.mfds.go.kr/brd/m_74/down.do?brd_id=ntc0003&seq=43915&data_tp=A&file_seq=2",
        "pics_di_2021.pdf": "https://picscheme.org/layout/document.php?id=1567"
    }
    
    for filename, url in urls.items():
        download_file(url, os.path.join(kb_dir, filename))
