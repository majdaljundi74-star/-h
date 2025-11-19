import sqlite3
import datetime
import logging
from typing import List, Tuple, Optional, Dict, Any

try:
    from config import DATABASE_NAME, USER_TITLES, logger
except ImportError:
    DATABASE_NAME = "anonymous_messages.db"
    USER_TITLES = {
        0: "🟢 مبتدئ", 5: "🔵 نشط", 10: "🟣 محبوب", 
        20: "🟠 نجم", 50: "🔴 أسطورة", 100: "👑 ملك الصراحة"
    }
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name: str = DATABASE_NAME):
        self.db_name = db_name
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_name, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                message_count INTEGER DEFAULT 0,
                user_title TEXT DEFAULT '🟢 مبتدئ',
                last_activity TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receiver_id INTEGER NOT NULL,
                sender_id INTEGER,
                message_text TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                banned_by INTEGER,
                ban_reason TEXT DEFAULT 'مخالفة شروط الاستخدام',
                banned_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                reporter_id INTEGER,
                reported_user_id INTEGER,
                reported_content TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                telegram_message_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (receiver_id, telegram_message_id)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", 
                      (user_id, username, first_name))
        conn.commit()
        conn.close()
    
    def update_user_stats(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ?", (user_id,))
        message_count = cursor.fetchone()[0]
        
        cursor.execute("UPDATE users SET message_count = ? WHERE user_id = ?", (message_count, user_id))
        
        title = self.get_user_title(message_count)
        cursor.execute("UPDATE users SET user_title = ? WHERE user_id = ?", (title, user_id))
        
        cursor.execute("UPDATE users SET last_activity = datetime('now') WHERE user_id = ?", (user_id,))
        
        conn.commit()
        conn.close()
        return message_count, title
    
    def get_user_title(self, message_count: int) -> str:
        for threshold, title in sorted(USER_TITLES.items(), reverse=True):
            if message_count >= threshold:
                return title
        return "🟢 مبتدئ"
    
    def get_next_title(self, message_count: int) -> tuple:
        thresholds = sorted(USER_TITLES.keys())
        for i, threshold in enumerate(thresholds):
            if message_count < threshold:
                next_threshold = threshold
                next_title = USER_TITLES[threshold]
                remaining = next_threshold - message_count
                return next_title, remaining
        return "🏆 أعلى مستوى", 0
    
    def get_user_info(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    def add_message(self, receiver_id: int, message_text: str, sender_id: int = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO messages (receiver_id, sender_id, message_text, created_at) VALUES (?, ?, ?, ?)",
                      (receiver_id, sender_id, message_text, timestamp))
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()
        
        self.update_user_stats(receiver_id)
        return message_id
    
    def save_message_delivery(self, message_id: int, receiver_id: int, telegram_message_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO message_deliveries (message_id, receiver_id, telegram_message_id) VALUES (?, ?, ?)",
                      (message_id, receiver_id, telegram_message_id))
        conn.commit()
        conn.close()
    
    def get_message_id_from_delivery(self, receiver_id: int, telegram_message_id: int) -> Optional[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT message_id FROM message_deliveries WHERE receiver_id = ? AND telegram_message_id = ?",
                      (receiver_id, telegram_message_id))
        result = cursor.fetchone()
        conn.close()
        return result['message_id'] if result else None
    
    def get_message_by_id(self, message_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    def is_banned(self, user_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def get_ban_info(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM banned_users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    def ban_user(self, user_id: int, banned_by: int, username: str = None, first_name: str = None, reason: str = "مخالفة شروط الاستخدام"):
        conn = self.get_connection()
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT OR REPLACE INTO banned_users (user_id, username, first_name, banned_by, ban_reason, banned_at) VALUES (?, ?, ?, ?, ?, ?)",
                      (user_id, username, first_name, banned_by, reason, timestamp))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم حظر المستخدم {user_id}")
    
    def unban_user(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"✅ تم رفع الحظر عن المستخدم {user_id}")
    
    def unban_all(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM banned_users")
        conn.commit()
        conn.close()
        logger.info("✅ تم رفع الحظر عن جميع المستخدمين")
    
    def get_banned_users(self, limit: int = 50):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM banned_users ORDER BY banned_at DESC LIMIT ?", (limit,))
        results = cursor.fetchall()
        conn.close()
        return [dict(row) for row in results]
    
    def add_report(self, message_id: int, reporter_id: int, reported_content: str, reported_user_id: Optional[int] = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO reports (message_id, reporter_id, reported_user_id, reported_content, created_at) VALUES (?, ?, ?, ?, ?)",
                      (message_id, reporter_id, reported_user_id, reported_content, timestamp))
        conn.commit()
        report_id = cursor.lastrowid
        conn.close()
        return report_id
    
    def get_report(self, report_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    def update_report_status(self, report_id: int, status: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE reports SET status = ?, reviewed_at = ? WHERE id = ?", (status, timestamp, report_id))
        conn.commit()
        conn.close()
    
    def get_pending_reports(self, limit: int = 20):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reports WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?", (limit,))
        results = cursor.fetchall()
        conn.close()
        return [dict(row) for row in results]
    
    def get_user_messages(self, user_id: int, limit: int = 50) -> List[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT message_text, created_at FROM messages WHERE receiver_id = ? ORDER BY created_at DESC LIMIT ?", 
                      (user_id, limit))
        messages = cursor.fetchall()
        conn.close()
        return messages
    
    def get_message_count(self, user_id: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM messages WHERE receiver_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result['count'] if result else 0
    
    def delete_user_messages(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE receiver_id = ?", (user_id,))
        conn.commit()
        deleted_count = cursor.rowcount
        conn.close()
        
        self.update_user_stats(user_id)
        return deleted_count
    
    def user_exists(self, user_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None