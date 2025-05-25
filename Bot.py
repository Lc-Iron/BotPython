import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ChatMemberHandler,
)
import datetime
import pytz
from collections import defaultdict
import time
import json
import os

# Configuração do token do bot
TOKEN = "8059197877:AAGTWOuC9JYABc2WWfFPIL6c_Klc_dWhl44"

# Configuração do fuso horário
TIMEZONE = pytz.timezone("America/Sao_Paulo")

# Lista de palavras proibidas
BAD_WORDS = ["palavrão1", "palavrão2", "ofensa"]  # Personalize aqui

# Limites para anti-spam
SPAM_LIMIT = 5
SPAM_TIME_WINDOW = 10

# Arquivo para armazenar triggers e estatísticas
TRIGGERS_FILE = "triggers.json"
STATS_FILE = "stats.json"

# Configuração de logging
logging.basicConfig(
    filename="bot_log.log",
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Armazenamento de avisos, estatísticas e triggers
warnings = defaultdict(int)
spam_tracker = defaultdict(list)
message_stats = defaultdict(int)
triggers = {}

# Carregar triggers e estatísticas de arquivos
def load_data():
    global triggers, message_stats
    if os.path.exists(TRIGGERS_FILE):
        with open(TRIGGERS_FILE, "r") as f:
            triggers.update(json.load(f))
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            message_stats.update(json.load(f))

def save_data():
    with open(TRIGGERS_FILE, "w") as f:
        json.dump(triggers, f)
    with open(STATS_FILE, "w") as f:
        json.dump(message_stats, f)

# Verifica se está no horário restrito (00h às 6h)
def is_restricted_time():
    now = datetime.datetime.now(TIMEZONE)
    return 0 <= now.hour < 6

# Verifica se o usuário é administrador
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    return chat_member.status in ["administrator", "creator"]

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bem-vindo ao bot de moderação! Eu restrinjo mensagens entre 00h e 6h, exceto para admins. "
        "Use /help para ver todos os comandos disponíveis."
    )
    logger.info(f"Comando /start executado por {update.effective_user.id}")

# Comando /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Comandos disponíveis:\n"
        "/start - Inicia o bot\n"
        "/help - Mostra esta mensagem\n"
        "/ban - Bane um usuário (responda à mensagem)\n"
        "/unban <user_id> - Desbane um usuário\n"
        "/mute <tempo> - Silencia um usuário (ex.: /mute 1h)\n"
        "/unmute - Desilencia um usuário\n"
        "/kick - Expulsa um usuário\n"
        "/warn - Avisa um usuário (3 avisos = ban)\n"
        "/clear - Limpa o histórico de avisos de um usuário\n"
        "/del - Deleta uma mensagem específica\n"
        "/purge - Deleta mensagens entre a mensagem respondida e o comando\n"
        "/pin - Fixa uma mensagem\n"
        "/settrigger <palavra> <resposta> - Cria um trigger\n"
        "/welcome <mensagem> - Configura mensagem de boas-vindas\n"
        "/stats - Exibe estatísticas do grupo\n"
        "/info - Mostra informações do usuário ou grupo\n"
        "/report - Reporta uma mensagem aos admins\n"
        "Mensagens entre 00h e 6h são restritas (exceto para admins)."
    )
    await update.message.reply_text(help_text)
    logger.info(f"Comando /help executado por {update.effective_user.id}")

# Boas-vindas a novos membros
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    for member in update.message.new_chat_members:
        welcome_message = triggers.get(f"{chat_id}_welcome", f"Bem-vindo, {member.full_name}! Leia as regras do grupo. Mensagens entre 00h e 6h são restritas.")
        await update.message.reply_text(welcome_message)
        logger.info(f"Novo membro: {member.id} ({member.full_name})")

# Filtro de mensagens (restrição de horário, palavras proibidas, anti-spam e triggers)
async def filter_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text.lower() if update.message.text else ""

    # Atualizar estatísticas de mensagens
    message_stats[user_id] += 1
    save_data()

    # Anti-spam
    current_time = time.time()
    spam_tracker[user_id].append(current_time)
    spam_tracker[user_id] = [t for t in spam_tracker[user_id] if current_time - t < SPAM_TIME_WINDOW]
    if len(spam_tracker[user_id]) > SPAM_LIMIT:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{update.effective_user.mention_html()}, pare de enviar mensagens tão rápido! Aguarde alguns segundos."
        )
        logger.info(f"Spam detectado: {user_id} enviou {len(spam_tracker[user_id])} mensagens")
        return

    # Filtro de palavras proibidas
    if any(bad_word in message_text for bad_word in BAD_WORDS):
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{update.effective_user.mention_html()}, mensagem deletada por conter palavras proibidas."
        )
        logger.info(f"Palavra proibida detectada: {user_id}")
        return

    # Restrição de horário (00h às 6h)
    if is_restricted_time() and not await is_admin(update, context):
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Mensagens não são permitidas entre 00h e 6h. Sua mensagem foi deletada."
        )
        logger.info(f"Mensagem deletada (horário restrito): {user_id}")
        return

    # Triggers
    chat_id_str = str(chat_id)
    for trigger_word, response in triggers.items():
        if trigger_word.startswith(chat_id_str) and trigger_word != f"{chat_id_str}_welcome":
            if trigger_word.split("_", 1)[1] in message_text:
                await update.message.reply_text(response)
                logger.info(f"Trigger acionado: {trigger_word} por {user_id}")

# Comando /ban
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message:
        user_to_ban = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_to_ban.id)
            await update.message.reply_text(f"{user_to_ban.full_name} foi banido.")
            logger.info(f"Usuário banido: {user_to_ban.id} por {update.effective_user.id}")
        except Exception as e:
            await update.message.reply_text(f"Erro ao banir: {str(e)}")
            logger.error(f"Erro ao banir {user_to_ban.id}: {str(e)}")
    else:
        await update.message.reply_text("Responda à mensagem do usuário que deseja banir.")

# Comando /unban
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if context.args:
        user_id = context.args[0]
        chat_id = update.effective_chat.id
        try:
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            await update.message.reply_text(f"Usuário {user_id} foi desbanido.")
            logger.info(f"Usuário desbanido: {user_id} por {update.effective_user.id}")
        except Exception as e:
            await update.message.reply_text(f"Erro ao desbanir: {str(e)}")
            logger.error(f"Erro ao desbanir {user_id}: {str(e)}")
    else:
        await update.message.reply_text("Forneça o ID do usuário para desbanir. Ex.: /unban 123456789")

# Comando /mute
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message and context.args:
        user_to_mute = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        duration = context.args[0].lower()
        until_date = None
        if duration.endswith("m"):
            minutes = int(duration[:-1])
            until_date = int(time.time() + minutes * 60)
        elif duration.endswith("h"):
            hours = int(duration[:-1])
            until_date = int(time.time() + hours * 3600)
        elif duration.endswith("d"):
            days = int(duration[:-1])
            until_date = int(time.time() + days * 86400)
        else:
            await update.message.reply_text("Formato inválido. Use: /mute 1h, /mute 30m, /mute 1d")
            return
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_to_mute.id,
                permissions={"can_send_messages": False},
                until_date=until_date
            )
            await update.message.reply_text(f"{user_to_mute.full_name} foi silenciado por {duration}.")
            logger.info(f"Usuário silenciado: {user_to_mute.id} por {duration} por {update.effective_user.id}")
        except Exception as e:
            await update.message.reply_text(f"Erro ao silenciar: {str(e)}")
            logger.error(f"Erro ao silenciar {user_to_mute.id}: {str(e)}")
    else:
        await update.message.reply_text("Responda à mensagem do usuário e forneça o tempo (ex.: /mute 1h).")

# Comando /unmute
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message:
        user_to_unmute = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_to_unmute.id,
                permissions={"can_send_messages": True}
            )
            await update.message.reply_text(f"{user_to_unmute.full_name} foi desilenciado.")
            logger.info(f"Usuário desilenciado: {user_to_unmute.id} por {update.effective_user.id}")
        except Exception as e:
            await update.message.reply_text(f"Erro ao desilenciar: {str(e)}")
            logger.error(f"Erro ao desilenciar {user_to_unmute.id}: {str(e)}")
    else:
        await update.message.reply_text("Responda à mensagem do usuário que deseja desilenciar.")

# Comando /kick
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message:
        user_to_kick = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_to_kick.id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_to_kick.id)
            await update.message.reply_text(f"{user_to_kick.full_name} foi expulso.")
            logger.info(f"Usuário expulso: {user_to_kick.id} por {update.effective_user.id}")
        except Exception as e:
            await update.message.reply_text(f"Erro ao expulsar: {str(e)}")
            logger.error(f"Erro ao expulsar {user_to_kick.id}: {str(e)}")
    else:
        await update.message.reply_text("Responda à mensagem do usuário que deseja expulsar.")

# Comando /warn
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message:
        user_to_warn = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        warnings[user_to_warn.id] += 1
        if warnings[user_to_warn.id] >= 3:
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_to_warn.id)
                await update.message.reply_text(f"{user_to_warn.full_name} recebeu 3 avisos e foi banido.")
                warnings[user_to_warn.id] = 0
                logger.info(f"Usuário banido por 3 avisos: {user_to_warn.id}")
            except Exception as e:
                await update.message.reply_text(f"Erro ao banir: {str(e)}")
                logger.error(f"Erro ao banir {user_to_warn.id}: {str(e)}")
        else:
            await update.message.reply_text(
                f"{user_to_warn.full_name} recebeu um aviso ({warnings[user_to_warn.id]}/3)."
            )
            logger.info(f"Aviso dado a {user_to_warn.id}: {warnings[user_to_warn.id]}/3")
    else:
        await update.message.reply_text("Responda à mensagem do usuário que deseja avisar.")

# Comando /clear
async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message:
        user_to_clear = update.message.reply_to_message.from_user
        warnings[user_to_clear.id] = 0
        await update.message.reply_text(f"Histórico de avisos de {user_to_clear.full_name} limpo.")
        logger.info(f"Histórico de avisos limpo: {user_to_clear.id} por {update.effective_user.id}")
    else:
        await update.message.reply_text("Responda à mensagem do usuário para limpar seus avisos.")

# Comando /del
async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=update.message.reply_to_message.message_id
            )
            await update.message.reply_text("Mensagem deletada.")
            logger.info(f"Mensagem deletada por {update.effective_user.id}")
        except Exception as e:
            await update.message.reply_text(f"Erro ao deletar mensagem: {str(e)}")
            logger.error(f"Erro ao deletar mensagem: {str(e)}")
    else:
        await update.message.reply_text("Responda à mensagem que deseja deletar.")

# Comando /purge
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message:
        chat_id = update.effective_chat.id
        start_message_id = update.message.reply_to_message.message_id
        end_message_id = update.message.message_id
        try:
            for message_id in range(start_message_id, end_message_id + 1):
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                except:
                    continue
            await update.message.reply_text("Mensagens entre a mensagem selecionada e este comando foram deletadas.")
            logger.info(f"Purge executado por {update.effective_user.id}")
        except Exception as e:
            await update.message.reply_text(f"Erro ao executar purge: {str(e)}")
            logger.error(f"Erro ao executar purge: {str(e)}")
    else:
        await update.message.reply_text("Responda à mensagem inicial para deletar mensagens até este comando.")

# Comando /pin
async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if update.message.reply_to_message:
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id,
                message_id=update.message.reply_to_message.message_id
            )
            await update.message.reply_text("Mensagem fixada.")
            logger.info(f"Mensagem fixada por {update.effective_user.id}")
        except Exception as e:
            await update.message.reply_text(f"Erro ao fixar mensagem: {str(e)}")
            logger.error(f"Erro ao fixar mensagem: {str(e)}")
    else:
        await update.message.reply_text("Responda à mensagem que deseja fixar.")

# Comando /settrigger
async def set_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if len(context.args) >= 2:
        trigger_word = context.args[0].lower()
        response = " ".join(context.args[1:])
        chat_id = str(update.effective_chat.id)
        triggers[f"{chat_id}_{trigger_word}"] = response
        save_data()
        await update.message.reply_text(f"Trigger '{trigger_word}' configurado com resposta: {response}")
        logger.info(f"Trigger configurado: {trigger_word} por {update.effective_user.id}")
    else:
        await update.message.reply_text("Use: /settrigger <palavra> <resposta>")

# Comando /welcome
async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Apenas administradores podem usar este comando.")
        return
    if context.args:
        welcome_message = " ".join(context.args)
        chat_id = str(update.effective_chat.id)
        triggers[f"{chat_id}_welcome"] = welcome_message
        save_data()
        await update.message.reply_text(f"Mensagem de boas-vindas configurada: {welcome_message}")
        logger.info(f"Mensagem de boas-vindas configurada por {update.effective_user.id}")
    else:
        await update.message.reply_text("Use: /welcome <mensagem>")

# Comando /stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = sorted(message_stats.items(), key=lambda x: x[1], reverse=True)[:5]
    stats_text = "Estatísticas do grupo:\n"
    for user_id, count in top_users:
        try:
            user = await context.bot.get_chat(user_id)
            stats_text += f"{user.full_name}: {count} mensagens\n"
        except:
            stats_text += f"Usuário {user_id}: {count} mensagens\n"
    await update.message.reply_text(stats_text)
    logger.info(f"Comando /stats executado por {update.effective_user.id}")

# Comando /info
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        info_text = (
            f"Informações do usuário:\n"
            f"Nome: {user.full_name}\n"
            f"ID: {user.id}\n"
            f"Avisos: {warnings[user.id]}/3\n"
            f"Mensagens enviadas: {message_stats[user.id]}"
        )
    else:
        chat = await context.bot.get_chat(chat_id)
        info_text = (
            f"Informações do grupo:\n"
            f"Nome: {chat.title}\n"
            f"ID: {chat.id}\n"
            f"Total de mensagens: {sum(message_stats.values())}"
        )
    await update.message.reply_text(info_text)
    logger.info(f"Comando /info executado por {update.effective_user.id}")

# Comando /report
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        reported_user = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_mentions = " ".join([f"@{admin.user.username}" for admin in admins if admin.user.username])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{update.effective_user.mention_html()} reportou uma mensagem de {reported_user.full_name}. Admins: {admin_mentions}"
        )
        logger.info(f"Report enviado por {update.effective_user.id} contra {reported_user.id}")
    else:
        await update.message.reply_text("Responda à mensagem que deseja reportar.")

def main():
    # Carregar dados
    load_data()

    # Inicializa o bot
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("warn", warn))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("del", delete_message))
    application.add_handler(CommandHandler("purge", purge))
    application.add_handler(CommandHandler("pin", pin))
    application.add_handler(CommandHandler("settrigger", set_trigger))
    application.add_handler(CommandHandler("welcome", set_welcome))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_messages))

    # Inicia o bot
    logger.info("Bot iniciado.")
    application.run_polling()

if __name__ == "__main__":
    main()