import json
import os
from pathlib import Path
from typing import Dict, Any

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account


DEFAULT_RMA_LOGS_FOLDER_ID = '19Q03v5KC2fVe2Q9btWzurvLP5hn7MnK2'
DRIVE_UPLOAD_URL = 'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true'


class GoogleDriveService:
    def __init__(self):
        self.folder_id = os.environ.get('GOOGLE_DRIVE_RMA_LOGS_FOLDER_ID', DEFAULT_RMA_LOGS_FOLDER_ID)
        self.credentials = self._load_credentials()

    def _load_credentials(self):
        scopes = ['https://www.googleapis.com/auth/drive']
        credentials_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if credentials_json:
            info = json.loads(credentials_json)
            return service_account.Credentials.from_service_account_info(info, scopes=scopes)

        base_dir = Path(__file__).resolve().parent
        credentials_path = base_dir / '../../credentials.json'
        return service_account.Credentials.from_service_account_file(str(credentials_path), scopes=scopes)

    @staticmethod
    def _sanitize_sn(sn_digital: str) -> str:
        base = ''.join(ch for ch in (sn_digital or '').strip() if ch.isalnum() or ch in ['-', '_'])
        return base or 'log_rma'

    def upload_rma_log_txt(self, file_storage, sn_digital: str) -> Dict[str, Any]:
        if not file_storage:
            return {'ok': False, 'message': 'Debe adjuntar archivo .txt de log'}

        filename = (file_storage.filename or '').strip()
        if not filename.lower().endswith('.txt'):
            return {'ok': False, 'message': 'El archivo de log debe ser .txt'}

        safe_sn = self._sanitize_sn(sn_digital)
        drive_filename = f'{safe_sn}.txt'

        try:
            content_bytes = file_storage.read() or b''
            file_storage.stream.seek(0)
        except Exception:
            return {'ok': False, 'message': 'No se pudo leer el archivo de log'}

        if not content_bytes:
            return {'ok': False, 'message': 'El archivo de log está vacío'}

        try:
            self.credentials.refresh(Request())
            token = self.credentials.token

            metadata = {
                'name': drive_filename,
                'parents': [self.folder_id]
            }

            files = {
                'metadata': ('metadata', json.dumps(metadata), 'application/json; charset=UTF-8'),
                'file': (drive_filename, content_bytes, 'text/plain')
            }

            headers = {'Authorization': f'Bearer {token}'}
            response = requests.post(DRIVE_UPLOAD_URL, headers=headers, files=files, timeout=30)
            if response.status_code not in (200, 201):
                return {
                    'ok': False,
                    'message': f'No se pudo subir log a Drive ({response.status_code}): {response.text[:200]}'
                }

            data = response.json()
            file_id = data.get('id')
            link = f'https://drive.google.com/file/d/{file_id}/view' if file_id else ''

            return {
                'ok': True,
                'file_id': file_id,
                'file_name': drive_filename,
                'link': link
            }
        except Exception as e:
            return {'ok': False, 'message': f'Error subiendo log a Drive: {str(e)}'}
