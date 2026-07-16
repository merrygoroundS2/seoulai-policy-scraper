# cron / launchd 설정 가이드

## macOS: cron 방식

### 1. crontab 편집
```bash
crontab -e
```

### 2. 매일 오전 8시 실행 (KST)
```
# AI 정책 기사 자동 스크랩 — 매일 08:00
0 8 * * * cd /Users/yunseungji/Desktop/동향지\ 자동\ 스크랩 && /usr/local/bin/python3 scripts/run_scrape.py >> logs/cron.log 2>&1
```

> ⚠️ **주의**: Mac 절전 모드에서는 cron이 실행되지 않습니다. `caffeinate` 사용을 권장합니다.

### 3. 절전 방지 + 실행
```
0 8 * * * caffeinate -s -t 600 cd /Users/yunseungji/Desktop/동향지\ 자동\ 스크랩 && python3 scripts/run_scrape.py >> logs/cron.log 2>&1
```

---

## macOS: launchd 방식 (권장)

cron보다 macOS에 더 적합한 launchd를 사용합니다.

### 1. plist 파일 생성
```bash
nano ~/Library/LaunchAgents/com.seoulai.scraper.plist
```

### 2. 내용
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.seoulai.scraper</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/Users/yunseungji/Desktop/동향지 자동 스크랩/scripts/run_scrape.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/yunseungji/Desktop/동향지 자동 스크랩</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/yunseungji/Desktop/동향지 자동 스크랩/logs/launchd_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/yunseungji/Desktop/동향지 자동 스크랩/logs/launchd_stderr.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

### 3. 등록 및 시작
```bash
launchctl load ~/Library/LaunchAgents/com.seoulai.scraper.plist
```

### 4. 확인
```bash
launchctl list | grep seoulai
```

### 5. 제거
```bash
launchctl unload ~/Library/LaunchAgents/com.seoulai.scraper.plist
```

---

## Linux: systemd timer 방식

### 1. 서비스 파일
```bash
sudo nano /etc/systemd/system/seoulai-scraper.service
```

```ini
[Unit]
Description=Seoul AI Policy Article Scraper
After=network-online.target

[Service]
Type=oneshot
User=deploy
WorkingDirectory=/opt/seoulai-scraper
ExecStart=/opt/seoulai-scraper/venv/bin/python scripts/run_scrape.py
Environment="TZ=Asia/Seoul"

[Install]
WantedBy=multi-user.target
```

### 2. 타이머 파일
```bash
sudo nano /etc/systemd/system/seoulai-scraper.timer
```

```ini
[Unit]
Description=Seoul AI Scraper Daily Timer

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### 3. 활성화
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now seoulai-scraper.timer
sudo systemctl status seoulai-scraper.timer
```

---

## Windows: Task Scheduler

1. `작업 스케줄러` 열기
2. `작업 만들기` 클릭
3. 트리거: 매일 08:00
4. 동작: `python.exe scripts\run_scrape.py`
5. 시작 위치: 프로젝트 폴더 경로
