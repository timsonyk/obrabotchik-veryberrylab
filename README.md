# Telegram Бот для обработки фотографий

Telegram бот для обработки фотографий клубники в шоколаде с использованием Google Gemini API.

## Возможности

- Обработка фотографий через Google Gemini AI
- Генерация нескольких вариантов обработанного изображения (от 1 до 10)
- Отправка результатов в двух форматах:
  - Сжатые (предпросмотр) - для быстрого просмотра
  - Без сжатия (документы) - для полного качества
- Настройки количества генерируемых вариантов
- Интуитивное меню с кнопками

## Структура проекта

```
Обработчик/
├── bot.py              # Основной файл бота
├── config.py           # Конфигурация
├── image_processor.py  # Модуль обработки изображений
├── obrabor.py         # Оригинальный скрипт обработки (для справки)
├── .env               # Переменные окружения
├── requirements.txt   # Зависимости
├── .gitignore        # Игнорируемые файлы
└── README.md         # Документация
```

## Установка

### 1. Клонирование/создание проекта

```bash
cd /Users/timofey/Desktop/Обработчик
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# или
venv\Scripts\activate  # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Откройте файл `.env` и добавьте необходимые ключи:

```env
BOTKEY=ваш_токен_телеграм_бота
GOOGLE_API_KEY=ваш_ключ_google_api
```

#### Как получить BOTKEY:
1. Откройте Telegram и найдите @BotFather
2. Отправьте команду `/newbot`
3. Следуйте инструкциям и получите токен

#### GOOGLE_API_KEY:
Ключ уже добавлен в файл, но для продакшена рекомендуется получить свой:
1. Перейдите на [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Создайте новый API ключ
3. Замените в `.env`

## Запуск

### Локальный запуск

```bash
python bot.py
```

Бот запустится и будет ожидать команды `/start` в Telegram.

## Деплой на VPS

### 1. Подключение к VPS

```bash
ssh user@your-vps-ip
```

### 2. Установка Python 3.11+

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
```

### 3. Загрузка проекта на VPS

Вариант 1: Через Git
```bash
git clone your-repository-url
cd Обработчик
```

Вариант 2: Через SCP
```bash
# На вашем локальном компьютере
scp -r /Users/timofey/Desktop/Обработчик user@your-vps-ip:~/
```

### 4. Установка зависимостей на VPS

```bash
cd ~/Обработчик
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Настройка автозапуска (systemd)

Создайте файл сервиса:

```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

Добавьте следующее содержимое:

```ini
[Unit]
Description=Telegram Image Processing Bot
After=network.target

[Service]
Type=simple
User=ваш_пользователь
WorkingDirectory=/home/ваш_пользователь/Обработчик
Environment="PATH=/home/ваш_пользователь/Обработчик/venv/bin"
ExecStart=/home/ваш_пользователь/Обработчик/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

Проверка статуса:

```bash
sudo systemctl status telegram-bot
```

Просмотр логов:

```bash
sudo journalctl -u telegram-bot -f
```

### 6. Альтернатива: Screen/Tmux

Если не хотите настраивать systemd:

```bash
# Установка screen
sudo apt install screen

# Запуск в фоновом режиме
screen -S telegram-bot
python bot.py

# Отсоединение: Ctrl+A, затем D
# Возврат к сессии: screen -r telegram-bot
```

## Использование бота

1. Найдите вашего бота в Telegram
2. Отправьте команду `/start`
3. Нажмите кнопку "Отправить фото"
4. Отправьте фотографию (желательно как документ для лучшего качества)
5. Дождитесь обработки (1-2 минуты)
6. Получите результаты:
   - Сначала сжатые версии (для быстрого просмотра)
   - Затем полноразмерные файлы

### Настройки

- Нажмите "Настройки" в главном меню
- Выберите "Количество фото"
- Укажите желаемое количество вариантов (1-10)

## Остановка бота

### Если запущен через systemd:
```bash
sudo systemctl stop telegram-bot
```

### Если запущен через screen:
```bash
screen -r telegram-bot
# Нажмите Ctrl+C
```

## Обновление бота на VPS

```bash
# Остановите бота
sudo systemctl stop telegram-bot

# Обновите код (через git или scp)
git pull  # если используете git

# Активируйте окружение и обновите зависимости
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Запустите снова
sudo systemctl start telegram-bot
```

## Мониторинг и обслуживание

### Логи
```bash
# Системные логи
sudo journalctl -u telegram-bot -f

# Проверка процессов
ps aux | grep bot.py
```

### Перезапуск при ошибках
```bash
sudo systemctl restart telegram-bot
```

## Устранение проблем

### Бот не отвечает
1. Проверьте статус: `sudo systemctl status telegram-bot`
2. Проверьте логи: `sudo journalctl -u telegram-bot -n 50`
3. Убедитесь, что BOTKEY корректен в `.env`

### Ошибки с Google API
1. Проверьте GOOGLE_API_KEY в `.env`
2. Убедитесь, что у вас есть доступ к Gemini API
3. Проверьте квоты API

### Проблемы с памятью
Если VPS имеет мало памяти, уменьшите MAX_WORKERS в `config.py`

## Безопасность

- Никогда не коммитьте `.env` файл в Git
- Используйте сильные пароли для VPS
- Регулярно обновляйте зависимости
- Настройте firewall на VPS

## Дополнительная информация

- [Документация aiogram](https://docs.aiogram.dev/)
- [Google Gemini API](https://ai.google.dev/)
- [Telegram Bot API](https://core.telegram.org/bots/api)

## Автор

Timofey

## Лицензия

MIT
