#!/usr/bin/env python3
"""监控记忆同步进度"""

import time
import psycopg2

def check_progress():
    conn = psycopg2.connect('postgresql://affinity:affinity_secret@localhost:5432/affinity')
    cur = conn.cursor()
    
    cur.execute("SELECT status, COUNT(*) FROM outbox_events GROUP BY status")
    stats = {row[0]: row[1] for row in cur.fetchall()}
    
    conn.close()
    return stats

print("🔄 开始监控记忆同步进度...\n")
print("按 Ctrl+C 停止监控\n")

try:
    last_done = 0
    while True:
        stats = check_progress()
        pending = stats.get('pending', 0)
        processing = stats.get('processing', 0)
        done = stats.get('done', 0)
        total = pending + processing + done
        
        progress = (done / total * 100) if total > 0 else 0
        speed = done - last_done
        last_done = done
        
        print(f"\r进度: {progress:.1f}% | Pending: {pending} | Processing: {processing} | Done: {done} | 速度: +{speed}/10s", end='', flush=True)
        
        if pending == 0 and processing == 0:
            print("\n\n✅ 所有记忆已同步完成！")
            break
        
        time.sleep(10)
        
except KeyboardInterrupt:
    print("\n\n⏸️  监控已停止")
