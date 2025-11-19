import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from functools import wraps

from database import Database
try:
    from config import REVIEW_BOT_TOKEN, REVIEW_ADMIN_IDS, logger
except ImportError:
    REVIEW_BOT_TOKEN = "8075818083:AAG3YIe0z_OObQiR9Ed9jw_pEBahPWNPmoY"
    REVIEW_ADMIN_IDS = [6174774057]
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

# تهيئة قاعدة البيانات
db = Database()

# ========== دوال بوت المراجعة ==========
def admin_required(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else None
        if user_id not in REVIEW_ADMIN_IDS:
            if update.message:
                await update.message.reply_text("❌ ليس لديك صلاحية استخدام هذا البوت.")
            elif update.callback_query:
                await update.callback_query.answer("❌ غير مسموح.", show_alert=True)
            return
        return await handler(update, context)
    return wrapper

def review_keyboard(report_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚫 حظر المرسل", callback_data=f"ban:{report_id}"),
        InlineKeyboardButton("✅ تجاهل البلاغ", callback_data=f"dismiss:{report_id}")
    ]])

def ban_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 قائمة المحظورين", callback_data="banned_list")],
        [InlineKeyboardButton("🔄 رفع الحظر عن الجميع", callback_data="unban_all")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")]
    ])

@admin_required
async def review_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("🤖 **بوت مراجعة الإبلاغات - لوحة التحكم**\n\n"
           "**الأوامر:**\n"
           "/pending - البلاغات المعلقة\n"
           "/ban <user_id> - حظر مستخدم\n" 
           "/unban <user_id> - رفع الحظر\n"
           "/banned - قائمة المحظورين\n"
           "/stats - إحصائيات النظام")
    await update.message.reply_text(text, reply_markup=ban_management_keyboard())

@admin_required
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ usage: /ban <user_id> [reason]")
        return
    try:
        user_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "مخالفة شروط الاستخدام"
        if db.is_banned(user_id):
            await update.message.reply_text("⚠️ محظور بالفعل.")
            return
        db.ban_user(user_id, update.effective_user.id, reason=reason)
        await update.message.reply_text(f"✅ تم حظر المستخدم `{user_id}`.\n**السبب:** {reason}", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ user_id يجب أن يكون رقماً.")

@admin_required
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ usage: /unban <user_id>")
        return
    try:
        user_id = int(context.args[0])
        if not db.is_banned(user_id):
            await update.message.reply_text("⚠️ غير محظور.")
            return
        db.unban_user(user_id)
        await update.message.reply_text(f"✅ تم رفع الحظر عن `{user_id}`.", parse_mode='Markdown')
    except ValueError:
        await update.message.reply_text("❌ user_id يجب أن يكون رقماً.")

@admin_required
async def banned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    banned_users = db.get_banned_users()
    if not banned_users:
        await update.message.reply_text("✅ لا يوجد محظورين.")
        return
    text = "👥 **قائمة المحظورين:**\n\n"
    for user in banned_users[:15]:
        text += f"👤 **User ID:** `{user['user_id']}`\n"
        text += f"📛 **الاسم:** {user.get('first_name', 'بدون اسم')}\n"
        text += f"📝 **السبب:** {user.get('ban_reason', 'مخالفة')}\n"
        text += f"⏰ **التاريخ:** {user.get('banned_at', 'غير معروف')}\n"
        text += "────────────────────\n"
    
    if len(banned_users) > 15:
        text += f"\n📊 ... وعرض {len(banned_users) - 15} مستخدم إضافي"
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 رفع الحظر عن الجميع", callback_data="unban_all"),
        InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")
    ]])
    
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')

@admin_required
async def list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reports = db.get_pending_reports()
    if not reports:
        await update.message.reply_text("✅ لا توجد بلاغات معلقة.")
        return
    
    await update.message.reply_text(f"📋 يوجد {len(reports)} بلاغ معلق:")
    
    for report in reports:
        msg_info = db.get_message_by_id(report["message_id"])
        message_text = msg_info["message_text"] if msg_info else report["reported_content"]
        created_at = msg_info["created_at"] if msg_info else report["created_at"]
        
        text = (f"📄 بلاغ رقم #{report['id']}\n"
               f"👤 المرسل المتهم: {report.get('reported_user_id', 'غير معروف')}\n"
               f"🧑‍💻 المُبلّغ: {report['reporter_id']}\n"
               f"🕒 التاريخ: {created_at}\n"
               f"النص:\n{message_text}")
        
        await update.message.reply_text(text, reply_markup=review_keyboard(report["id"]))

@admin_required
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات النظام"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_activity > datetime('now', '-7 days')")
    active_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM messages")
    total_messages = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM messages WHERE created_at > datetime('now', '-1 days')")
    today_messages = cursor.fetchone()[0]
    
    cursor.execute("SELECT status, COUNT(*) FROM reports GROUP BY status")
    report_stats = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM banned_users")
    banned_count = cursor.fetchone()[0]
    
    conn.close()
    
    text = "📊 **إحصائيات النظام الشاملة:**\n\n"
    text += f"👥 **إجمالي المستخدمين:** {total_users}\n"
    text += f"🔵 **المستخدمين النشطين (أسبوع):** {active_users}\n"
    text += f"💌 **إجمالي الرسائل:** {total_messages}\n"
    text += f"📨 **الرسائل اليوم:** {today_messages}\n"
    text += f"🚫 **المستخدمين المحظورين:** {banned_count}\n\n"
    
    text += "📋 **حالات البلاغات:**\n"
    for status, count in report_stats:
        text += f"• {status}: {count}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

@admin_required
async def handle_review_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    logger.info(f"🔘 ضغط على زر في بوت المراجعة: {data}")
    
    if data.startswith("ban:"):
        report_id = int(data.split(":")[1])
        await process_ban_action(query, report_id)
    elif data.startswith("dismiss:"):
        report_id = int(data.split(":")[1])
        await process_dismiss_action(query, report_id)
    elif data == "banned_list":
        await banned_command(query, context)
    elif data == "unban_all":
        await process_unban_all(query)
    elif data == "stats":
        await stats_command(query, context)

async def process_ban_action(query, report_id: int):
    try:
        report = db.get_report(report_id)
        if not report:
            await query.edit_message_text("❌ لم يتم العثور على البلاغ.")
            return
        
        if report["status"] != "pending":
            await query.edit_message_text("ℹ️ تم التعامل مع هذا البلاغ سابقاً.")
            return
        
        reported_user_id = report.get("reported_user_id")
        if not reported_user_id:
            await query.edit_message_text("❌ لا يوجد معرف للمستخدم لحظره.")
            return
        
        if db.is_banned(reported_user_id):
            db.update_report_status(report_id, "already_banned")
            await query.edit_message_text(f"⚠️ المستخدم {reported_user_id} محظور بالفعل.\n✅ تم تحديث حالة البلاغ.")
            return
        
        admin_id = query.from_user.id
        db.ban_user(reported_user_id, admin_id, reason="مخالفة شروط الاستخدام بناءً على بلاغ")
        db.update_report_status(report_id, "banned")
        
        await query.edit_message_text(
            f"✅ تم حظر المستخدم `{reported_user_id}` بنجاح.\n"
            f"📋 البلاغ #{report_id} تم معالجته.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في عملية الحظر: {e}")
        await query.edit_message_text("❌ حدث خطأ أثناء معالجة الحظر.")

async def process_dismiss_action(query, report_id: int):
    try:
        report = db.get_report(report_id)
        if not report:
            await query.edit_message_text("❌ لم يتم العثور على البلاغ.")
            return
        
        if report["status"] != "pending":
            await query.edit_message_text("ℹ️ تم التعامل مع هذا البلاغ سابقاً.")
            return
        
        db.update_report_status(report_id, "dismissed")
        await query.edit_message_text(f"✅ تم تجاهل البلاغ #{report_id} بنجاح.")
        
    except Exception as e:
        logger.error(f"❌ خطأ في عملية التجاهل: {e}")
        await query.edit_message_text("❌ حدث خطأ أثناء معالجة التجاهل.")

async def process_unban_all(query):
    try:
        db.unban_all()
        await query.edit_message_text("✅ تم رفع الحظر عن جميع المستخدمين بنجاح.")
    except Exception as e:
        logger.error(f"❌ خطأ في رفع الحظر عن الجميع: {e}")
        await query.edit_message_text("❌ حدث خطأ أثناء رفع الحظر عن الجميع.")

def main():
    """تشغيل بوت المراجعة"""
    if not REVIEW_BOT_TOKEN:
        logger.error("❌ يرجى ضبط REVIEW_BOT_TOKEN قبل تشغيل بوت المراجعة.")
        return
    
    try:
        application = Application.builder().token(REVIEW_BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", review_start))
        application.add_handler(CommandHandler("pending", list_pending))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("ban", ban_command))
        application.add_handler(CommandHandler("unban", unban_command))
        application.add_handler(CommandHandler("banned", banned_command))
        application.add_handler(CallbackQueryHandler(handle_review_actions))
        
        logger.info("👮 بوت مراجعة الإبلاغات يعمل الآن...")
        
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"❌ خطأ في بوت المراجعة: {e}")

if __name__ == '__main__':
    main()