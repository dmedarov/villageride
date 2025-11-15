# VillageRide V2 (Осойца)

Просто уеб приложение за споделени превози в с. Осойца – шофьори предлагат превози, пътници публикуват заявки "Търся превоз". Картата използва OpenStreetMap + Leaflet, а бекендът е Flask + SQLite.

## Локално стартиране

```bash
python -m venv venv
source venv/bin/activate  # на Windows: venv\Scripts\activate
pip install -r requirements.txt

export FLASK_ENV=development
export SECRET_KEY="some-secret"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="admin123"

python app.py
```

Отвори в браузър:

- Публична част: http://127.0.0.1:5000
- Админ панел: http://127.0.0.1:5000/admin

## Docker

```bash
docker build -t villageride .
docker run -p 5000:5000 \
  -e SECRET_KEY="some-secret" \
  -e ADMIN_USERNAME="admin" \
  -e ADMIN_PASSWORD="admin123" \
  villageride
```

## База данни

Използва `village_ride.db` (SQLite файл в същата директория). Схемата се създава автоматично при първо стартиране.
