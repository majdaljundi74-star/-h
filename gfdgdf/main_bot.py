import datetime
import logging
import httpx
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from database import Database
try:
    from config import BOT_TOKEN, BOT_USERNAME, MESSAGES, REVIEW_BOT_TOKEN, REVIEW_ADMIN_IDS, DEVELOPER_USERNAME, logger
except ImportError:
    BOT_TOKEN = "8012650476:AAFYbxQhtVwamBRqa5oCx36efCVmw3oOH-w"
    BOT_USERNAME = "Vgcfihvbot"
    REVIEW_BOT_TOKEN = "8075818083:AAG3YIe0z_OObQiR9Ed9jw_pEBahPWNPmoY"
    REVIEW_ADMIN_IDS = [6174774057]
    DEVELOPER_USERNAME = "@gK_IH"
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    MESSAGES = {
        "welcome": "اهلاً بك في البوت...",
        "banned_user_message": f"🚫 تم حظرك. تواصل مع {DEVELOPER_USERNAME}",
        # ... باقي الرسائل
    }

# تهيئة قاعدة البيانات
db = Database()

# ========== دوال البوت الرئيسي ==========
def get_user_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=user_{user_id}"

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📥 رسائلي", callback_data="my_messages"),
         InlineKeyboardButton("🔗 رابط الصراحة", callback_data="my_link")],
        [InlineKeyboardButton("📊 عدد الرسائل", callback_data="message_count"),
         InlineKeyboardButton("🗑️ حذف الجميع", callback_data="delete_all")],
        [InlineKeyboardButton("🏆 إحصائياتي", callback_data="my_stats"),
         InlineKeyboardButton("ℹ️ معلومات", callback_data="info")],
        [InlineKeyboardButton("🔏 سياسة الخصوصية", callback_data="privacy"),
         InlineKeyboardButton("📝 شروط الاستخدام", callback_data="terms")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_rating(message_count: int) -> str:
    if message_count >= 100:
        return "⭐⭐⭐⭐⭐"
    elif message_count >= 50:
        return "⭐⭐⭐⭐"
    elif message_count >= 20:
        return "⭐⭐⭐"
    elif message_count >= 10:
        return "⭐⭐"
    elif message_count >= 5:
        return "⭐"
    else:
        return "بدون تقييم"

async def notify_review_team(report_id: int, message_data: dict, reporter_id: int, receiver_id: int, telegram_message_id: int) -> bool:
    if not REVIEW_BOT_TOKEN or not REVIEW_ADMIN_IDS:
        return False
    
    reported_user_id = message_data.get("sender_id", "غير معروف")
    message_text = message_data.get("message_text", "رسالة غير نصية")
    
    text = (f"🚨 بلاغ جديد رقم #{report_id}\n\n"
           f"👤 المرسل المتهم: {reported_user_id}\n"
           f"📨 صاحب الرابط: {receiver_id}\n"
           f"🧑‍💻 المُبلّغ: {reporter_id}\n\n"
           f"النص:\n{message_text}")
    
    reply_markup = {"inline_keyboard": [[
        {"text": "🚫 حظر المرسل", "callback_data": f"ban:{report_id}"},
        {"text": "✅ تجاهل البلاغ", "callback_data": f"dismiss:{report_id}"}
    ]]}
    
    url = f"https://api.telegram.org/bot{REVIEW_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=30.0) as client:
        for admin_id in REVIEW_ADMIN_IDS:
            try:
                await client.post(url, json={"chat_id": admin_id, "text": text, "reply_markup": reply_markup})
                logger.info(f"✅ تم إرسال البلاغ #{report_id} إلى المشرف {admin_id}")
                return True
            except Exception:
                continue
    return False

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if db.is_banned(user_id):
        await update.message.reply_text(MESSAGES["banned_user_message"])
        return
    
    db.add_user(user_id, user.username, user.first_name)
    context.user_data.pop('receiver_id', None)
    context.user_data.pop('waiting_for_message', None)
    
    message_count, title = db.update_user_stats(user_id)
    
    user_info = db.get_user_info(user_id)
    if user_info:
        old_title = user_info.get('user_title', '🟢 مبتدئ')
        if old_title != title:
            await update.message.reply_text(
                f"🎉 **تهانينا!** \n\nلقد وصلت إلى مستوى جديد: {title} \n📊 عدد رسائلك: {message_count}",
                reply_markup=get_main_keyboard()
            )
            return
    
    if context.args and len(context.args) > 0:
        start_param = context.args[0]
        if start_param.startswith("user_"):
            try:
                receiver_id = int(start_param.split("_", 1)[1])
                if db.is_banned(receiver_id):
                    await update.message.reply_text("❌ صاحب هذا الرابط محظور.")
                    return
                if not db.user_exists(receiver_id):
                    db.add_user(receiver_id)
                await update.message.reply_text(
                    "اكتب رسالتك المجهولة وسيتم إرسالها دون الكشف عن هويتك.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="cancel_send")]])
                )
                context.user_data['receiver_id'] = receiver_id
                context.user_data['waiting_for_message'] = True
                return
            except (ValueError, IndexError):
                pass
    
    await update.message.reply_text(MESSAGES["welcome"], reply_markup=get_main_keyboard())

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if db.is_banned(user_id):
        await update.message.reply_text(MESSAGES["banned_user_message"])
        return
    
    message_count, title = db.update_user_stats(user_id)
    next_title, remaining = db.get_next_title(message_count)
    rating = get_user_rating(message_count)
    
    user_info = db.get_user_info(user_id)
    join_date = user_info.get('created_at', 'غير معروف') if user_info else 'غير معروف'
    
    stats_text = (f"📊 **إحصائياتك الشخصية:**\n\n"
                 f"💌 إجمالي الرسائل: {message_count}\n"
                 f"🏆 لقبك الحالي: {title}\n"
                 f"📈 المستوى التالي: {next_title} بعد {remaining} رسالة\n"
                 f"⭐ تقييمك: {rating}\n"
                 f"🕒 مشترك منذ: {join_date}")
    
    await update.message.reply_text(stats_text, reply_markup=get_main_keyboard())

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if db.is_banned(user_id):
        await update.message.reply_text(MESSAGES["banned_user_message"])
        return
    user_link = get_user_link(user_id)
    await update.message.reply_text(f"✅ تم إنشاء رابطك الخاص!\n\n🔗 رابط الصراحة الخاص بك:\n{user_link}", reply_markup=get_main_keyboard())

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if db.is_banned(user_id):
        await update.message.reply_text(MESSAGES["banned_user_message"])
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ يجب الرد على رسالة للإبلاغ عنها.")
        return
    
    replied_message = update.message.reply_to_message
    if not replied_message.from_user or not replied_message.from_user.is_bot:
        await update.message.reply_text("❌ هذه ليست رسالة صراحة مجهولة.")
        return
    
    receiver_id = update.effective_user.id
    telegram_message_id = replied_message.message_id
    message_id = db.get_message_id_from_delivery(receiver_id, telegram_message_id)
    
    if not message_id:
        await update.message.reply_text("❌ هذه ليست رسالة صراحة مجهولة.")
        return
    
    message_data = db.get_message_by_id(message_id)
    if not message_data:
        await update.message.reply_text("❌ هذه ليست رسالة صراحة مجهولة.")
        return
    
    reported_user_id = message_data.get("sender_id")
    if not reported_user_id:
        await update.message.reply_text("❌ لا يمكن تحديد المرسل.")
        return
    
    report_id = db.add_report(message_id, receiver_id, message_data.get("message_text", "رسالة غير نصية"), reported_user_id)
    await update.message.reply_text("✅ تم إرسال البلاغ إلى فريق المراجعة.")
    
    success = await notify_review_team(report_id, message_data, receiver_id, receiver_id, telegram_message_id)
    if not success:
        await update.message.reply_text("⚠️ تم تسجيل البلاغ لكن تعذر إرسال إشعار للمشرف.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    message_text = update.message.text
    
    if db.is_banned(user_id):
        await update.message.reply_text(MESSAGES["banned_user_message"])
        return
    
    if context.user_data.get('waiting_for_message') and context.user_data.get('receiver_id'):
        receiver_id = context.user_data['receiver_id']
        message_id = db.add_message(receiver_id, message_text, sender_id=user_id)
        
        now = datetime.datetime.now()
        timestamp = f"{now.strftime('%Y/%m/%d')} - {now.hour if now.hour <= 12 else now.hour - 12}:{now.strftime('%M')}:{now.strftime('%S')} {'AM' if now.hour < 12 else 'PM'}"
        message_to_send = f"💌 وصلتك رسالة جديدة\n\n\n⏱️ وقت الرسالة: {timestamp}\n\n----\n\n\n{message_text}\n\n\n----"
        
        try:
            sent_message = await context.bot.send_message(chat_id=receiver_id, text=message_to_send)
            db.save_message_delivery(message_id, receiver_id, sent_message.message_id)
            await update.message.reply_text("✅ تم إرسال رسالتك بنجاح!", reply_markup=get_main_keyboard())
        except Exception as e:
            await update.message.reply_text("❌ لم يتم إرسال الرسالة.", reply_markup=get_main_keyboard())
        
        context.user_data.pop('receiver_id', None)
        context.user_data.pop('waiting_for_message', None)
        return
    
    await update.message.reply_text("▪️ رسالة غير مفهومة .", reply_markup=get_main_keyboard())

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if db.is_banned(user_id):
        await query.edit_message_text(MESSAGES["banned_user_message"])
        return
    
    if data == "my_link":
        user_link = get_user_link(user_id)
        await query.edit_message_text(f"✅ تم إنشاء رابطك الخاص!\n\n🔗 رابط الصراحة الخاص بك:\n{user_link}", reply_markup=get_main_keyboard())
    
    elif data == "my_messages":
        messages = db.get_user_messages(user_id)
        if not messages:
            text = "📭 لا توجد رسائل بعد.\n\nشارك رابطك مع الآخرين لبدء استقبال الرسائل!"
        else:
            text = "📥 رسائلك المجهولة:\n\n"
            for idx, msg in enumerate(messages[:10], 1):
                text += f"{idx}. \"{msg[0]}\"\n   ⏰ {msg[1]}\n\n"
            if len(messages) > 10:
                text += f"\n📊 إجمالي الرسائل: {len(messages)}"
        await query.edit_message_text(text, reply_markup=get_main_keyboard())
    
    elif data == "message_count":
        count = db.get_message_count(user_id)
        await query.edit_message_text(f"📊 عدد الرسائل المستلمة: {count}", reply_markup=get_main_keyboard())
    
    elif data == "delete_all":
        deleted_count = db.delete_user_messages(user_id)
        await query.edit_message_text(f"🗑️ تم حذف جميع الرسائل بنجاح!\n\n🗑️ تم حذف {deleted_count} رسالة.", reply_markup=get_main_keyboard())
    
    elif data == "my_stats":
        message_count, title = db.update_user_stats(user_id)
        next_title, remaining = db.get_next_title(message_count)
        rating = get_user_rating(message_count)
        
        user_info = db.get_user_info(user_id)
        join_date = user_info.get('created_at', 'غير معروف') if user_info else 'غير معروف'
        
        stats_text = (f"📊 **إحصائياتك الشخصية:**\n\n"
                     f"💌 إجمالي الرسائل: {message_count}\n"
                     f"🏆 لقبك الحالي: {title}\n"
                     f"📈 المستوى التالي: {next_title} بعد {remaining} رسالة\n"
                     f"⭐ تقييمك: {rating}\n"
                     f"🕒 مشترك منذ: {join_date}")
        await query.edit_message_text(stats_text, reply_markup=get_main_keyboard())
    
    elif data == "info":
        user_link = get_user_link(user_id)
        count = db.get_message_count(user_id)
        text = f"ℹ️ معلومات البوت:\n\n🔗 رابطك الخاص:\n{user_link}\n\n📊 عدد الرسائل: {count}"
        await query.edit_message_text(text, reply_markup=get_main_keyboard())
    
    elif data == "privacy":
        await query.edit_message_text("🔐 سياسة الخصوصية...", reply_markup=get_main_keyboard())
    
    elif data == "terms":
        await query.edit_message_text("📝 شروط الاستخدام...", reply_markup=get_main_keyboard())
    
    elif data == "cancel_send":
        context.user_data.pop('receiver_id', None)
        context.user_data.pop('waiting_for_message', None)
        await query.edit_message_text("❌ تم إلغاء الإرسال.", reply_markup=get_main_keyboard())

def main():
    """تشغيل البوت الرئيسي"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("link", link_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("report", report_command))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("🚀 البوت الرئيسي يعمل الآن...")
        
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"❌ خطأ في البوت الرئيسي: {e}")

if __name__ == '__main__':
    main()