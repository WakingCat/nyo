import pandas as pd
from datetime import datetime
from app import db
from app.models.miner import Miner

class WarrantyService:
    def import_warranties_from_excel(self, file_path):
        """
        Importa fechas de garantía desde un Excel.
        Intenta buscar en hoja 'data', sino lee la primera.
        Espera columnas: 'SN' (o similar) y 'Garantía' (o 'Warranty').
        """
        try:
            # Primero intentar detectar hojas
            xl = pd.ExcelFile(file_path)
            sheet_names = xl.sheet_names
            
            target_sheet = 0 # Default primera hoja
            
            # Buscar hoja 'data' (case insensitive)
            for s in sheet_names:
                if 'data' in s.lower():
                    target_sheet = s
                    break
            
            df = pd.read_excel(file_path, sheet_name=target_sheet)
            sheet_read = target_sheet if isinstance(target_sheet, str) else sheet_names[0]
            
            # Normalizar columnas a minúsculas para búsqueda flexible
            original_columns = list(df.columns)
            df.columns = df.columns.astype(str).str.lower().str.strip()
            
            # Buscar columna SN
            col_sn = next((c for c in df.columns if 'sn' in c or 'serial' in c), None)
            # Buscar columna Garantia
            col_garantia = next((c for c in df.columns if 'garant' in c or 'warranty' in c), None)
            
            if not col_sn or not col_garantia:
                return {
                    'status': 'error', 
                    'message': f'Error en hoja "{sheet_read}": Faltan columnas (SN, Garantia). Encontradas: {list(original_columns)}'
                }
                
            count_updated = 0
            errors = []
            
            for index, row in df.iterrows():
                sn = str(row[col_sn]).strip()
                fecha_raw = row[col_garantia]
                
                if pd.isna(fecha_raw) or sn == 'nan' or sn == '':
                    continue
                    
                # Parsear fecha
                expiry_date = None
                try:
                    if isinstance(fecha_raw, datetime):
                        expiry_date = fecha_raw.date()
                    else:
                        # Intentar parsear string
                        expiry_date = pd.to_datetime(fecha_raw).date()
                except Exception as e:
                    # errors.append(f"Fila {index+2}: Error fecha '{fecha_raw}' para SN {sn}")
                    continue
                    
                if not expiry_date:
                    continue
                    
                # Buscar minero
                # Buscamos por SN físico exacto primero
                miner = Miner.query.filter_by(sn_fisica=sn).first()
                if miner:
                    miner.garantia_vence = expiry_date
                    count_updated += 1
            
            db.session.commit()
            
            result_msg = 'ok'
            if count_updated == 0:
                result_msg = 'warning'
                errors.insert(0, f"Se leyó la hoja '{sheet_read}' pero ningún SN del Excel coincidió con la base de datos.")

            return {
                'status': result_msg, 
                'updated': count_updated, 
                'errors': errors[:10] # Top 10 errores
            }
            
        except Exception as e:
            return {'status': 'error', 'message': f'Error procesando archivo: {str(e)}'}

warranty_service = WarrantyService()
