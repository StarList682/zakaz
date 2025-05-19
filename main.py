import asyncio
import time
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.bot import DefaultBotProperties
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram import types
from telebot import TeleBot
from telebot.types import BotCommand

CONSTRUCTOR_TOKEN = "7811075054:AAHu-f0MGkeTGvlqzbgIBdeLiXBobrNK5vM"
bot = TeleBot(CONSTRUCTOR_TOKEN)

import config
from data_store import data, load_data, save_data, add_user, get_user, update_username, record_event

bot.set_my_commands([
    BotCommand("start",     "📖 Меню"),
    BotCommand("cancel",    "❌ Отменить текущее действие")
])


import logging
logging.basicConfig(level=logging.INFO)

class CaptchaState(StatesGroup):
    waiting_answer = State()
    waiting_channels = State()

class SellState(StatesGroup):
    waiting_text = State()

class BuyState(StatesGroup):
    waiting_text = State()

class PinState(StatesGroup):
    waiting_forward = State()

class AdminState(StatesGroup):
    waiting_ban_user = State()
    waiting_unban_user = State()
    waiting_new_admin = State()
    waiting_give_sub_user = State()
    waiting_give_sub_details = State()
    waiting_broadcast_msg = State()
    waiting_add_channel = State()

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher(bot=bot)

@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    current = await state.get_state()
    if not current:
        return
    await state.clear()
    await message.answer("✅ Действие отменено.", reply_markup=types.ReplyKeyboardRemove())
    await send_main_menu(message.from_user.id)

def subscription_active(user):
    """Check if user has an active subscription and return tier if yes, else None."""
    sub = user.get("subscription", {})
    tier = sub.get("tier")
    exp = sub.get("expires")
    if not tier or not exp:
        return None
    if int(time.time()) >= exp:
        user["subscription"] = {"tier": None, "expires": None}
        save_data()
        return None
    return tier

async def send_main_menu(chat_id: int):
    """Send the main menu to user with greeting and inline buttons. Delete old menu if exists."""
    user = get_user(chat_id)
    if not user:
        return
    old_menu_id = user.get("menu_message_id")
    if old_menu_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_menu_id)
        except Exception:
            pass
    first_name = user.get("first_name", "")
    unique_id = user.get("unique_id")
    text = (f"Здравствуйте, <b>{first_name}</b>!\n"
            f"Ваш уникальный ID: <code>{unique_id}</code>\n"
            "Выберите действие:")
    buttons = [
        [types.InlineKeyboardButton(text="Предложить продажу", callback_data="sell_offer"),
         types.InlineKeyboardButton(text="Предложить покупку", callback_data="buy_offer")],
        [types.InlineKeyboardButton(text="Подписки", callback_data="subscriptions"),
         types.InlineKeyboardButton(text="Реферальная ссылка", callback_data="referral")],
        [types.InlineKeyboardButton(text="Закрепить объявление", callback_data="pin_ad"),
         types.InlineKeyboardButton(text="Профиль", callback_data="profile")],
        [types.InlineKeyboardButton(text="Правила", callback_data="rules"),
         types.InlineKeyboardButton(text="Поддержка", callback_data="support")]
    ]
    if chat_id in data.get("admins", []):
        buttons.append([types.InlineKeyboardButton(text="Админ-панель", callback_data="admin_panel")])
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    sent = await bot.send_message(chat_id, text, reply_markup=keyboard)
    user["menu_message_id"] = sent.message_id
    save_data()
    return sent

async def send_admin_panel(chat_id: int):
    """Send admin panel main menu to admin user. Delete old menu if exists."""
    user = get_user(chat_id)
    if not user:
        return
    old_admin_msg = user.get("admin_message_id")
    if old_admin_msg:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=old_admin_msg)
        except Exception:
            pass
    text = "<b>Админ-панель</b>"
    buttons = [
        [types.InlineKeyboardButton(text="Забанить", callback_data="admin_ban"),
         types.InlineKeyboardButton(text="Разбанить", callback_data="admin_unban")],
        [types.InlineKeyboardButton(text="Добавить админа", callback_data="admin_add"),
         types.InlineKeyboardButton(text="Выдать подписку", callback_data="admin_give_sub")],
        [types.InlineKeyboardButton(text="Аналитика", callback_data="admin_stats"),
         types.InlineKeyboardButton(text="Рассылка", callback_data="admin_broadcast")],
        [types.InlineKeyboardButton(text="Обязательные каналы", callback_data="admin_channels")],
        [types.InlineKeyboardButton(text="Назад", callback_data="admin_back")]
    ]
    kb = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    sent = await bot.send_message(chat_id, text, reply_markup=kb)
    user["admin_message_id"] = sent.message_id
    save_data()
    return sent

def ensure_pin_cycle(user):
    """Reset pin usage count if a month has passed since last reset."""
    now = int(time.time())
    start = user.get("pins_cycle_start")
    if start is None:
        user["pins_cycle_start"] = now
        user["pins_used"] = 0
        return
    if now - start >= config.PIN_CYCLE_SECONDS:
        user["pins_used"] = 0
        user["pins_cycle_start"] = now
        save_data()

#######################################
# Programed by https://t.me/SAKI_n_tosh
#######################################

@dp.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    referral_code = args[1] if len(args) > 1 else None
    user_id = message.from_user.id
    first_name = message.from_user.first_name or ""
    username = message.from_user.username
    user = get_user(user_id)
    if user and user.get("banned"):
        await message.answer("Вы забанены и не можете пользоваться ботом. Обратитесь в поддержку для разбана.")
        return
    if not user:
        referrer_id = None
        if referral_code:
 
            for uid, udata in data["users"].items():
                if udata.get("unique_id") == referral_code:
                    referrer_id = int(uid)
                    break
        user = add_user(user_id, first_name, username=username, referrer_id=referrer_id)
    else:

        user["first_name"] = first_name
        update_username(user_id, username)
        save_data()
    if not user.get("captcha_passed"):
        import random
        a = random.randint(1, 9)
        b = random.randint(1, 9)
        op = random.choice(["+", "-"])
        if op == "-":

            if b > a:
                a, b = b, a
        question = f"{a} {op} {b}"
        solution = str(eval(question))

        await message.answer(f"Пройдите капчу: <b>{question}</b> = ?")

        await state.set_state(CaptchaState.waiting_answer)
        await state.update_data(solution=solution)
        return

    if not user.get("channels_verified"):

        text = ("✅ Капча пройдена.\n"
                "Теперь подпишитесь на каналы и нажмите кнопку ниже:\n")
        for ch in data.get("mandatory_channels", []):
            text += f"➡️ <a href=\"https://t.me/{ch}\">{ch}</a>\n"
        keyboard = types.InlineKeyboardMarkup(
            inline_keyboard=[[types.InlineKeyboardButton(text="Проверить подписку", callback_data="check_subs")]]
        )
        await message.answer(text, reply_markup=keyboard)
        await state.set_state(CaptchaState.waiting_channels)
        return

    await send_main_menu(user_id)

@dp.message(CaptchaState.waiting_answer)
async def process_captcha_answer(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        return

    if user.get("banned"):
        await state.clear()
        await message.answer("Вы забанены и не можете пользоваться ботом.")
        return

    data_state = await state.get_data()
    correct = data_state.get("solution")
    if not message.text or message.text.strip() != correct:
        await message.answer("Неверно. Попробуйте еще раз.")
        return 
    user["captcha_passed"] = True
    save_data()

    text = ("✅ Капча пройдена.\n"
            "Подпишитесь на следующие каналы:\n")
    for ch in data.get("mandatory_channels", []):
        text += f"➡️ <a href=\"https://t.me/{ch}\">{ch}</a>\n"
    text += "После этого нажмите кнопку ниже."
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Проверить подписку", callback_data="check_subs")]]
    )
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(CaptchaState.waiting_channels)

#------------------------------------------------------------

@dp.callback_query(F.data == "check_subs")
async def on_check_subs(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if not user:
        return

 
    if not user.get("captcha_passed"):
        await callback.answer("Сначала пройдите капчу.", show_alert=True)
        return

    mandatory = ["@sellfrilance", "@buyfrilance"]
    missing = []

    for ch in mandatory:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=callback.from_user.id)
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except Exception:
            missing.append(ch)

    if missing:
        await callback.answer(
            f"❗️ Подпишитесь на канал(ы): {', '.join(missing)}",
            show_alert=True
        )
        return

    # Все подписки пройдены
    user["channels_verified"] = True
    save_data()

    await callback.answer()
    await callback.message.edit_text("✅ Подписки на каналы подтверждены.")
    await send_main_menu(callback.from_user.id)
    await state.clear()

@dp.callback_query(F.data == "sell_offer")
async def on_sell_offer(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await callback.answer("Вы забанены.", show_alert=True)
        return

    cur_state = await state.get_state()
    if cur_state:
        await callback.answer("Завершите текущий процесс перед началом нового.", show_alert=True)
        return

    if user.get("menu_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["menu_message_id"] = None
    await callback.answer()
    if user.get("username"):
        prompt = ("Отправьте текст объявления о продаже, которое вы хотите разместить.\n"
                  "Ваш username будет добавлен автоматически.")
    else:
        prompt = ("Отправьте текст объявления о продаже, которое вы хотите разместить.\n"
                  "У вас нет username, не забудьте указать контакт для связи в тексте.")
    await bot.send_message(callback.from_user.id, prompt)
    await state.set_state(SellState.waiting_text)

@dp.message(SellState.waiting_text)
async def handle_sell_text(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await state.clear()
        await message.answer("Вы были забанены. Отправка объявления отменена.")
        return
    text = message.text
    if not text or text.strip() == "":
        await message.answer("Текст объявления не должен быть пустым. Попробуйте снова.")
        return
    contact_info = ""
    if user.get("username"):
        contact_info = f"\nКонтакт: @{user['username']}"
    try:
        sent = await bot.send_message(config.SELL_CHANNEL, text + contact_info)
    except Exception as e:
        await message.answer("Ошибка при публикации объявления в канал.")
        await state.clear()
        await send_main_menu(message.from_user.id)
        return
    user["posts_count"] += 1
    user["posts"].append({"chat_id": sent.chat.id, "msg_id": sent.message_id})
    save_data()
    channel_username = config.SELL_CHANNEL
    await message.answer(
    f"✅ Ваше объявление опубликовано в канале @{channel_username}:contentReference[oaicite:4]{{index=4}}:\n"
    f"https://t.me/{channel_username}/{sent.message_id}"
    )
    await state.clear()
    await send_main_menu(message.from_user.id)


@dp.callback_query(F.data == "buy_offer")
async def on_buy_offer(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await callback.answer("Вы забанены.", show_alert=True)
        return
    cur_state = await state.get_state()
    if cur_state:
        await callback.answer("Завершите текущий процесс сначала.", show_alert=True)
        return
    if user.get("menu_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["menu_message_id"] = None
    await callback.answer()
    if user.get("username"):
        prompt = ("Отправьте текст объявления о покупке, которое вы хотите разместить.\n"
                  "Ваш username будет добавлен автоматически.")
    else:
        prompt = ("Отправьте текст объявления о покупке, которое вы хотите разместить.\n"
                  "У вас нет username, укажите контакт для связи в тексте.")
    await bot.send_message(callback.from_user.id, prompt)
    await state.set_state(BuyState.waiting_text)

@dp.message(BuyState.waiting_text)
async def handle_buy_text(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await state.clear()
        await message.answer("Вы были забанены. Отправка объявления отменена.")
        return
    text = message.text
    if not text or text.strip() == "":
        await message.answer("Текст объявления не должен быть пустым.")
        return
    contact_info = ""
    if user.get("username"):
        contact_info = f"\nКонтакт: @{user['username']}"
    try:
        sent = await bot.send_message(config.BUY_CHANNEL, text + contact_info)
    except Exception:
        await message.answer("Ошибка при публикации объявления в канал.")
        await state.clear()
        await send_main_menu(message.from_user.id)
        return
    user["posts_count"] += 1
    user["posts"].append({"chat_id": sent.chat.id, "msg_id": sent.message_id})
    save_data()
    channel_username = config.BUY_CHANNEL
    await message.answer(f"✅ Ваше объявление опубликовано в канале @{channel_username}:\n"
                         f"https://t.me/{channel_username}/{sent.message_id}")
    await state.clear()
    await send_main_menu(message.from_user.id)

@dp.callback_query(F.data == "subscriptions")
async def on_subscriptions(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await callback.answer("Вы забанены.", show_alert=True)
        return
    if user.get("menu_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["menu_message_id"] = None
    await callback.answer()
    text = ("<b>Подписки</b>\n"
            "Выберите уровень подписки:")
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="База", callback_data="subs_base"),
             types.InlineKeyboardButton(text="Классический", callback_data="subs_classic"),
             types.InlineKeyboardButton(text="Про", callback_data="subs_pro")],
            [types.InlineKeyboardButton(text="Назад", callback_data="subs_back_main")]
        ]
    )
    await bot.send_message(callback.from_user.id, text, reply_markup=kb)

@dp.callback_query(F.data == "subs_back_main")
async def on_subs_back_main(callback: CallbackQuery):
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass
    await send_main_menu(callback.from_user.id)

@dp.callback_query(F.data.startswith("subs_") & ~F.data.endswith("_main"))
async def on_subs_tier_select(callback: CallbackQuery):
    tier = callback.data.split("_", 1)[1]
    if tier not in ("base", "classic", "pro"):
        return
    await callback.answer()
    prices = config.SUBSCRIPTION_PRICES.get(tier, {})
    text = f"<b>Тариф '{tier.capitalize()}'</b>\nВыберите срок подписки:"
    buttons = []
    for days, cost in prices.items():
        # Label: e.g. "1 месяц - 30⭐"
        label = ""
        if days % 30 == 0:
            months = days // 30
            if months == 1:
                label = f"1 месяц - {cost}⭐"
            else:
                label = f"{months} мес. - {cost}⭐"
        else:
            label = f"{days} дн. - {cost}⭐"
        cb_data = f"buy_sub_{tier}_{days}"
        buttons.append([types.InlineKeyboardButton(text=label, callback_data=cb_data)])
    buttons.append([types.InlineKeyboardButton(text="Назад", callback_data="subs_back")])
    kb = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "subs_back")
async def on_subs_back(callback: CallbackQuery):
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass
    await on_subscriptions(callback)

@dp.callback_query(F.data.startswith("buy_sub_"))
async def on_buy_subscription(callback: CallbackQuery):
    # Data format: buy_sub_<tier>_<days>
    parts = callback.data.split("_")
    if len(parts) != 4:
        return
    _, _, tier, days_str = parts
    try:
        days = int(days_str)
    except:
        return
    if tier not in config.SUBSCRIPTION_PRICES or days not in config.SUBSCRIPTION_PRICES[tier]:
        await callback.answer("Неверный выбор.", show_alert=True)
        return
    cost = config.SUBSCRIPTION_PRICES[tier][days]
    prices = [LabeledPrice(label=f"{tier.capitalize()} {days} дней", amount=cost)]
    payload = f"sub:{tier}:{days}"
    await bot.send_invoice(callback.from_user.id,
                            title=f"Подписка {tier.capitalize()}",
                            description=f"Оформление подписки '{tier}' на {days} дней.",
                            provider_token="",  
                            currency="XTR",
                            prices=prices,
                            start_parameter=f"{tier}-{days}",
                            payload=payload)
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass

@dp.callback_query(F.data == "referral")
async def on_referral(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await callback.answer("Вы забанены.", show_alert=True)
        return
    if user.get("menu_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["menu_message_id"] = None
    await callback.answer()
    me = await bot.get_me()
    bot_username = me.username
    ref_code = user["unique_id"]
    link = f"https://t.me/{bot_username}?start={ref_code}"
    refs = user.get("referrals", [])
    ref_list_text = ""
    if refs:
        ref_list_text = "\n\nВаши рефералы:\n"
        for uid in refs:
            ref_user = get_user(uid)
            if ref_user:
                name = ref_user.get("first_name") or ""
                uname = ref_user.get("username")
                if uname:
                    ref_list_text += f"• @{uname} ({name})\n"
                else:
                    ref_list_text += f"• {name} (ID: {ref_user['unique_id']})\n"
    else:
        ref_list_text = "\n\nПока нет рефералов."
    text = (f"Ваша реферальная ссылка:\n{link}" +
            ref_list_text)
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Назад", callback_data="ref_back")]]
    )
    await bot.send_message(callback.from_user.id, text, reply_markup=kb)

@dp.callback_query(F.data == "ref_back")
async def on_ref_back(callback: CallbackQuery):
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass
    await send_main_menu(callback.from_user.id)

@dp.callback_query(F.data == "pin_ad")
async def on_pin_request(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await callback.answer("Вы забанены.", show_alert=True)
        return
    cur_state = await state.get_state()
    if cur_state:
        await callback.answer("Сначала завершите предыдущий процесс.", show_alert=True)
        return
    tier = subscription_active(user)
    if tier not in ("classic", "pro"):
        await callback.answer()
        await bot.send_message(callback.from_user.id, 
                               "Закрепление объявлений доступно только для тарифов 'Classic' и 'Pro'.")
        return
    ensure_pin_cycle(user)
    used = user.get("pins_used", 0)
    if tier == "pro":
        if used >= 5:
            await callback.answer("Лимит закреплений исчерпан (5/5).", show_alert=True)
            return
        await callback.answer()
        await bot.send_message(callback.from_user.id, 
                               "Перешлите сюда ваше объявление из канала, которое хотите закрепить.")
        await state.set_state(PinState.waiting_forward)
    elif tier == "classic":
        if used >= 5:
            await callback.answer("Лимит закреплений исчерпан (5/5) на этот месяц.", show_alert=True)
            return
        await callback.answer()
        await bot.send_message(callback.from_user.id, 
                               f"Перешлите сюда ваше объявление из канала для закрепления. Стоимость: {config.PIN_PRICE}⭐.")
        await state.set_state(PinState.waiting_forward)

@dp.message(PinState.waiting_forward)
async def handle_pin_forward(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await state.clear()
        await message.answer("Вы были забанены. Операция закрепления отменена.")
        return
    if not message.forward_from_chat:
        await message.reply("Пожалуйста, перешлите сообщение объявления из канала.")
        return
    forward_chat = message.forward_from_chat
    chat_username = forward_chat.username
    valid_channels = [config.SELL_CHANNEL.lower(), config.BUY_CHANNEL.lower()]
    if chat_username:
        if chat_username.lower() not in valid_channels:
            await message.reply("Это объявление не из поддерживаемых каналов.")
            return
    else:
        if forward_chat.id not in [c.get("chat_id") for c in user.get("posts", [])]:
            await message.reply("Это объявление не из поддерживаемых каналов.")
            return
    found = False
    for post in user.get("posts", []):
        if post.get("chat_id") == forward_chat.id and post.get("msg_id") == message.forward_from_message_id:
            found = True
            break
    if not found:
        await message.reply("Это объявление не было опубликовано с вашего аккаунта.")
        return
    tier = subscription_active(user)
    if tier == "pro":
        try:
            await bot.pin_chat_message(chat_id=forward_chat.id, message_id=message.forward_from_message_id)
        except Exception as e:
            await message.reply("Не удалось закрепить сообщение. Проверьте права бота.")
            await state.clear()
            await send_main_menu(message.from_user.id)
            return
        user["pins_used"] += 1
        if user.get("pins_cycle_start") is None:
            user["pins_cycle_start"] = int(time.time())
        save_data()
        await message.answer("✅ Объявление закреплено (использовано закрепов: {}/5).".format(user["pins_used"]))
        await state.clear()
        await send_main_menu(message.from_user.id)
    elif tier == "classic":

        chan_id = forward_chat.id
        msg_id = message.forward_from_message_id
        payload = f"pin:{chan_id}:{msg_id}"
        prices = [LabeledPrice(label="Закрепить объявление", amount=config.PIN_PRICE)]
        await bot.send_invoice(message.from_user.id,
                                title="Закрепление объявления",
                                description="Оплата за закрепление объявления в канале",
                                provider_token="",  
                                currency="XTR",
                                prices=prices,
                                payload=payload,
                                start_parameter="pin-ad")
        await state.clear()
        await message.answer("После оплаты ваше объявление будет закреплено.")

@dp.callback_query(F.data == "profile")
async def on_profile(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await callback.answer("Вы забанены.", show_alert=True)
        return
    if user.get("menu_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["menu_message_id"] = None
    await callback.answer()
    sub_status = "Нет"
    tier = subscription_active(user)
    if tier:
        exp = user["subscription"].get("expires")
        if exp:
            remaining = (exp - int(time.time())) // 3600  # hours
            days_left = remaining // 24 + 1
            sub_status = f"{tier.capitalize()} (осталось ~{days_left} дн.)"
        else:
            sub_status = f"{tier.capitalize()}"
    pins_info = ""
    if tier in ("classic", "pro"):
        ensure_pin_cycle(user)
        used = user.get("pins_used", 0)
        pins_info = f"{used}/5 использовано в этом месяце"
    else:
        pins_info = "Недоступно"
    posts_count = user.get("posts_count", 0)
    text = (f"<b>Профиль</b>\n"
            f"ID: <code>{user['unique_id']}</code>\n"
            f"Подписка: {sub_status}\n"
            f"Закрепы (исп/макс в мес): {pins_info}\n"
            f"Публикаций сделано: {posts_count}")
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Назад", callback_data="prof_back")]]
    )
    await bot.send_message(callback.from_user.id, text, reply_markup=kb)

@dp.callback_query(F.data == "prof_back")
async def on_profile_back(callback: CallbackQuery):
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass
    await send_main_menu(callback.from_user.id)

@dp.callback_query(F.data == "rules")
async def on_rules(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await callback.answer("Вы забанены.", show_alert=True)
        return
    if user.get("menu_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["menu_message_id"] = None
    await callback.answer()
    text = ("<b>Правила</b>\n"
            "❌ Запрещены к публикации и обсуждению: детская порнография, провокационные материалы, нецензурная лексика.\n"
            "❗ Нарушение правил приведет к бану без предупреждения.\n"
            "💬 Разбан возможен за 500⭐ через поддержку @kuladvuka.")
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Назад", callback_data="rules_back")]]
    )
    await bot.send_message(callback.from_user.id, text, reply_markup=kb)

@dp.callback_query(F.data == "rules_back")
async def on_rules_back(callback: CallbackQuery):
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass
    await send_main_menu(callback.from_user.id)

@dp.callback_query(F.data == "support")
async def on_support(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("banned"):
        await callback.answer("Вы забанены.", show_alert=True)
        return
    if user.get("menu_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["menu_message_id"] = None
    await callback.answer()
    text = "По всем вопросам поддержки и разбана обращайтесь: @kuladvuka"
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Назад", callback_data="support_back")]]
    )
    await bot.send_message(callback.from_user.id, text, reply_markup=kb)

@dp.callback_query(F.data == "support_back")
async def on_support_back(callback: CallbackQuery):
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass
    await send_main_menu(callback.from_user.id)

@dp.callback_query(F.data == "admin_panel")
async def on_admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in data.get("admins", []):
        await callback.answer("Недоступно.", show_alert=True)
        return
    user = get_user(callback.from_user.id)
    if not user:
        return
    if user.get("menu_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["menu_message_id"] = None
    await callback.answer()
    await send_admin_panel(callback.from_user.id)

@dp.callback_query(F.data == "admin_back")
async def on_admin_back(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if user and user.get("admin_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["admin_message_id"] = None
    await callback.answer()
    await send_main_menu(callback.from_user.id)

@dp.callback_query(F.data == "admin_ban")
async def on_admin_ban(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    user = get_user(callback.from_user.id)
    if user and user.get("admin_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["admin_message_id"] = None
    await bot.send_message(callback.from_user.id, "Отправьте ID или @username пользователя для бана:")
    await state.set_state(AdminState.waiting_ban_user)

@dp.message(AdminState.waiting_ban_user)
async def admin_ban_user_input(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in data.get("admins", []):
        await state.clear()
        return
    target = message.text.strip()
    target_user = None
    if target.startswith("@"):
        uname = target[1:]
        for u in data["users"].values():
            if u.get("username", "").lower() == uname.lower():
                target_user = u
                break
    elif target.isdigit():
        target_user = get_user(int(target))
    if not target_user:
        await message.answer("Пользователь не найден.")
        return
    tid = target_user["id"]
    if tid in data.get("admins", []):
        await message.answer("Нельзя забанить администратора.")
        await state.clear()
        await send_admin_panel(admin_id)
        return
    if target_user.get("banned"):
        await message.answer("Этот пользователь уже забанен.")
    else:
        target_user["banned"] = True
        save_data()
        await message.answer(f"Пользователь {target_user['unique_id']} забанен.")
    await state.clear()
    await send_admin_panel(admin_id)

@dp.callback_query(F.data == "admin_unban")
async def on_admin_unban(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    user = get_user(callback.from_user.id)
    if user and user.get("admin_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["admin_message_id"] = None
    await bot.send_message(callback.from_user.id, "Отправьте ID или @username пользователя для разбана:")
    await state.set_state(AdminState.waiting_unban_user)

@dp.message(AdminState.waiting_unban_user)
async def admin_unban_user_input(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in data.get("admins", []):
        await state.clear()
        return
    target = message.text.strip()
    target_user = None
    if target.startswith("@"):
        uname = target[1:]
        for u in data["users"].values():
            if u.get("username", "").lower() == uname.lower():
                target_user = u
                break
    elif target.isdigit():
        target_user = get_user(int(target))
    if not target_user:
        await message.answer("Пользователь не найден.")
        return
    tid = target_user["id"]
    if not target_user.get("banned"):
        await message.answer("Этот пользователь не находится в бане.")
    else:
        target_user["banned"] = False
        save_data()
        await message.answer(f"Пользователь {target_user['unique_id']} разбанен.")
    await state.clear()
    await send_admin_panel(admin_id)

@dp.callback_query(F.data == "admin_add")
async def on_admin_add(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    user = get_user(callback.from_user.id)
    if user and user.get("admin_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["admin_message_id"] = None
    await bot.send_message(callback.from_user.id, "Отправьте ID или @username пользователя для добавления в админы:")
    await state.set_state(AdminState.waiting_new_admin)

@dp.message(AdminState.waiting_new_admin)
async def admin_add_user_input(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in data.get("admins", []):
        await state.clear()
        return
    target = message.text.strip()
    target_id = None
    if target.startswith("@"):
        uname = target[1:]
        for u in data["users"].values():
            if u.get("username", "").lower() == uname.lower():
                target_id = u["id"]
                break
    elif target.isdigit():
        target_id = int(target)
    if not target_id:
        await message.answer("Пользователь не найден.")
        return
    if target_id in data.get("admins", []):
        await message.answer("Этот пользователь уже админ.")
    else:
        data["admins"].append(target_id)
        save_data()
        await message.answer("Пользователь добавлен в админы.")
    await state.clear()
    await send_admin_panel(admin_id)

@dp.callback_query(F.data == "admin_give_sub")
async def on_admin_give_sub(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    user = get_user(callback.from_user.id)
    if user and user.get("admin_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["admin_message_id"] = None
    await bot.send_message(callback.from_user.id, "Отправьте ID или @username пользователя для выдачи подписки:")
    await state.set_state(AdminState.waiting_give_sub_user)

@dp.message(AdminState.waiting_give_sub_user)
async def admin_give_sub_user_input(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in data.get("admins", []):
        await state.clear()
        return
    target = message.text.strip()
    target_user = None
    if target.startswith("@"):
        uname = target[1:]
        for u in data["users"].values():
            if u.get("username", "").lower() == uname.lower():
                target_user = u
                break
    elif target.isdigit():
        target_user = get_user(int(target))
    if not target_user:
        await message.answer("Пользователь не найден.")
        return
    await state.update_data(target_id=target_user["id"])
    await message.answer("Укажите тариф и срок в днях (например: pro 30):")
    await state.set_state(AdminState.waiting_give_sub_details)

@dp.message(AdminState.waiting_give_sub_details)
async def admin_give_sub_details_input(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in data.get("admins", []):
        await state.clear()
        return
    content = message.text.strip().split()
    if len(content) < 2:
        await message.answer("Неверный формат. Пример: pro 30")
        return
    tier = content[0].lower()
    days_str = content[1]
    try:
        days = int(days_str)
    except:
        await message.answer("Некорректное число дней.")
        return
    if tier not in ("base", "classic", "pro"):
        await message.answer("Некорректный тип подписки. Используйте base/classic/pro.")
        return
    data_state = await state.get_data()
    target_id = data_state.get("target_id")
    target_user = get_user(target_id) if target_id else None
    if not target_user:
        await message.answer("Ошибка: пользователь не найден.")
        await state.clear()
        await send_admin_panel(admin_id)
        return
    now = int(time.time())
    if subscription_active(target_user):
        if target_user["subscription"]["tier"] == tier:
            target_user["subscription"]["expires"] = target_user["subscription"]["expires"] + days*24*3600
        else:
            target_user["subscription"] = {"tier": tier, "expires": now + days*24*3600}
    else:
        target_user["subscription"] = {"tier": tier, "expires": now + days*24*3600}
    save_data()
    record_event("subscription", tier=tier, user_id=target_user["id"])
    await message.answer(f"Выдана подписка {tier} на {days} дн. пользователю {target_user['unique_id']}.")
    await state.clear()
    await send_admin_panel(admin_id)

@dp.callback_query(F.data == "admin_stats")
async def on_admin_stats(callback: CallbackQuery):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    user = get_user(callback.from_user.id)
    if user and user.get("admin_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["admin_message_id"] = None
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="День", callback_data="stats_day"),
         types.InlineKeyboardButton(text="Месяц", callback_data="stats_month"),
         types.InlineKeyboardButton(text="Год", callback_data="stats_year"),
         types.InlineKeyboardButton(text="Все время", callback_data="stats_all")],
        [types.InlineKeyboardButton(text="Назад", callback_data="stats_back")]
    ])
    await bot.send_message(callback.from_user.id, "Период аналитики:", reply_markup=kb)

def compute_stats(period_days=None):
    now = int(time.time())
    start_time = 0 if period_days is None else now - period_days*24*3600
    users_count = 0
    for u in data["users"].values():
        if u.get("joined_at", 0) >= start_time:
            users_count += 1
    subs_count = {"base": 0, "classic": 0, "pro": 0}
    for event in data.get("events", []):
        if event.get("type") == "subscription":
            t = event.get("tier")
            ttime = event.get("time", 0)
            if t and ttime >= start_time:
                subs_count[t] = subs_count.get(t, 0) + 1
    return users_count, subs_count

@dp.callback_query(F.data.in_({"stats_day", "stats_month", "stats_year", "stats_all"}))
async def on_stats_period(callback: CallbackQuery):
    if callback.from_user.id not in data.get("admins", []):
        return
    period = callback.data.split("_")[1]
    period_days = None
    label = ""
    if period == "day":
        period_days = 1
        label = "за последние 24 ч"
    elif period == "month":
        period_days = 30
        label = "за последние 30 дней"
    elif period == "year":
        period_days = 365
        label = "за последние 365 дней"
    elif period == "all":
        period_days = None
        label = "за все время"
    users_count, subs_count = compute_stats(period_days)
    text = (f"<b>Аналитика {label}</b>\n"
            f"Новых пользователей: {users_count}\n"
            "Подписки:\n"
            f"• База: {subs_count.get('base', 0)}\n"
            f"• Classic: {subs_count.get('classic', 0)}\n"
            f"• Pro: {subs_count.get('pro', 0)}")
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Назад", callback_data="stats_back")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "stats_back")
async def on_stats_back(callback: CallbackQuery):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass
    await send_admin_panel(callback.from_user.id)

@dp.callback_query(F.data == "admin_broadcast")
async def on_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    user = get_user(callback.from_user.id)
    if user and user.get("admin_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["admin_message_id"] = None
    await bot.send_message(callback.from_user.id, "Отправьте текст рассылки для всех пользователей:")
    await state.set_state(AdminState.waiting_broadcast_msg)

@dp.message(AdminState.waiting_broadcast_msg)
async def admin_broadcast_send(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in data.get("admins", []):
        await state.clear()
        return
    text = message.text
    if not text:
        await message.answer("Сообщение не должно быть пустым.")
        return
    count = 0
    fail = 0
    for uid_str in data["users"].keys():
        uid = int(uid_str)
        try:
            await bot.send_message(uid, text)
            count += 1
        except Exception:
            fail += 1
    await message.answer(f"Сообщение разослано {count} пользователям. Не удалось: {fail}.")
    await state.clear()
    await send_admin_panel(admin_id)

@dp.callback_query(F.data == "admin_channels")
async def on_admin_channels(callback: CallbackQuery):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    user = get_user(callback.from_user.id)
    if user and user.get("admin_message_id") == callback.message.message_id:
        try:
            await bot.delete_message(callback.from_user.id, callback.message.message_id)
        except:
            pass
        user["admin_message_id"] = None
    channel_list = data.get("mandatory_channels", [])
    text = "<b>Обязательные каналы</b> (пользователи должны быть на них подписаны):\n"
    if channel_list:
        for i, ch in enumerate(channel_list, start=1):
            text += f"{i}. {ch}\n"
    else:
        text += "Нет обязательных каналов."
    kb_buttons = []
    for idx, ch in enumerate(channel_list):
        kb_buttons.append([types.InlineKeyboardButton(text=f"Удалить {ch}", callback_data=f"remchan_{idx}")])
    kb_buttons.append([types.InlineKeyboardButton(text="Добавить канал", callback_data="addchan")])
    kb_buttons.append([types.InlineKeyboardButton(text="Назад", callback_data="channels_back")])
    kb = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    await bot.send_message(callback.from_user.id, text, reply_markup=kb)

@dp.callback_query(F.data.startswith("remchan_"))
async def on_remove_channel(callback: CallbackQuery):
    if callback.from_user.id not in data.get("admins", []):
        return
    idx_str = callback.data.split("_", 1)[1]
    try:
        idx = int(idx_str)
    except:
        await callback.answer()
        return
    channels = data.get("mandatory_channels", [])
    if 0 <= idx < len(channels):
        removed = channels.pop(idx)
        save_data()
        await callback.answer(f"Канал {removed} удален из обязательных.", show_alert=True)
        text = "<b>Обязательные каналы</b>:\n"
        if channels:
            for i, ch in enumerate(channels, start=1):
                text += f"{i}. {ch}\n"
        else:
            text += "Нет обязательных каналов."
        kb_buttons = []
        for idx, ch in enumerate(channels):
            kb_buttons.append([types.InlineKeyboardButton(text=f"Удалить {ch}", callback_data=f"remchan_{idx}")])
        kb_buttons.append([types.InlineKeyboardButton(text="Добавить канал", callback_data="addchan")])
        kb_buttons.append([types.InlineKeyboardButton(text="Назад", callback_data="channels_back")])
        kb = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
        await callback.message.edit_text(text, reply_markup=kb)
    else:
        await callback.answer()

@dp.callback_query(F.data == "addchan")
async def on_add_channel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    await state.update_data(channels_msg_id=callback.message.message_id)
    await bot.send_message(callback.from_user.id, "Отправьте @username или ссылку на канал:")
    await state.set_state(AdminState.waiting_add_channel)

@dp.message(AdminState.waiting_add_channel)
async def admin_add_channel_input(message: Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in data.get("admins", []):
        await state.clear()
        return
    text = message.text.strip()
    if text.startswith("http"):
        # example: https://t.me/channelname
        part = text.split("t.me/")[-1]
        if "/" in part:
            part = part.split("/")[0]
        username = part
    else:
        username = text.lstrip("@")
    if not username:
        await message.answer("Некорректное имя канала.")
        return
    try:
        chat = await bot.get_chat(username)
        if chat.type != "channel":
            raise ValueError("Not a channel")
    except Exception as e:
        await message.answer("Ошибка: не удалось получить информацию о канале. Убедитесь, что бот является администратором канала.")
        return
    if username in data["mandatory_channels"]:
        await message.answer("Канал уже в списке.")
    else:
        data["mandatory_channels"].append(username)
        save_data()
        await message.answer(f"Канал @{username} добавлен в список обязательных.")
        data_state = await state.get_data()
        msg_id = data_state.get("channels_msg_id")
        if msg_id:
            channels = data["mandatory_channels"]
            text = "<b>Обязательные каналы</b>:\n"
            if channels:
                for i, ch in enumerate(channels, start=1):
                    text += f"{i}. {ch}\n"
            else:
                text += "Нет обязательных каналов."
            kb_buttons = []
            for idx, ch in enumerate(channels):
                kb_buttons.append([types.InlineKeyboardButton(text=f"Удалить {ch}", callback_data=f"remchan_{idx}")])
            kb_buttons.append([types.InlineKeyboardButton(text="Добавить канал", callback_data="addchan")])
            kb_buttons.append([types.InlineKeyboardButton(text="Назад", callback_data="channels_back")])
            kb = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
            try:
                await bot.edit_message_text(text, admin_id, msg_id, reply_markup=kb)
            except:
                pass
    await state.clear()
    await send_admin_panel(admin_id)

@dp.callback_query(F.data == "channels_back")
async def on_channels_back(callback: CallbackQuery):
    if callback.from_user.id not in data.get("admins", []):
        return
    await callback.answer()
    try:
        await bot.delete_message(callback.from_user.id, callback.message.message_id)
    except:
        pass
    await send_admin_panel(callback.from_user.id)

@dp.message(F.content_type == "successful_payment")
async def on_successful_payment(message: Message):
    sp = message.successful_payment
    if not sp:
        return
    payload = sp.invoice_payload
    if payload.startswith("sub:"):
        # Format: sub:tier:days
        _, tier, days_str = payload.split(":")
        days = int(days_str)
        user = get_user(message.from_user.id)
        if not user:
            return
        now = int(time.time())
        if subscription_active(user):
            if user["subscription"]["tier"] == tier:
                user["subscription"]["expires"] += days * 24 * 3600
            else:
                user["subscription"] = {"tier": tier, "expires": now + days*24*3600}
        else:
            user["subscription"] = {"tier": tier, "expires": now + days*24*3600}
        save_data()
        record_event("subscription", tier=tier, user_id=message.from_user.id)
        await message.reply(f"✅ Подписка <b>{tier.capitalize()}</b> оформлена на {days} дн.")
        await send_main_menu(message.from_user.id)
    elif payload.startswith("pin:"):
        _, chat_id_str, msg_id_str = payload.split(":")
        try:
            chat_id = int(chat_id_str)
            msg_id = int(msg_id_str)
        except:
            return
        user = get_user(message.from_user.id)
        if not user:
            return
        if subscription_active(user) != "classic":
            await message.reply("Ошибка: ваша подписка 'Classic' не активна.")
            return
        ensure_pin_cycle(user)
        if user.get("pins_used", 0) >= 5:
            await message.reply("Вы уже использовали 5 закреплений в этом месяце.")
            return
        try:
            await bot.pin_chat_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            await message.reply("Не удалось закрепить сообщение. (Бот имеет права администратора?)")
            return
        user["pins_used"] = user.get("pins_used", 0) + 1
        if not user.get("pins_cycle_start"):
            user["pins_cycle_start"] = int(time.time())
        save_data()
        await message.reply("✅ Ваше объявление закреплено в канале.")
        await send_main_menu(message.from_user.id)

@dp.message(Command("cancel"))
async def cancel_action(message: Message, state: FSMContext):
    cur_state = await state.get_state()
    if not cur_state:
        return
    target_menu = "main"
    if cur_state and cur_state.startswith("AdminState"):
        target_menu = "admin"
    await state.clear()
    await message.answer("Действие отменено.")
    if target_menu == "admin":
        await send_admin_panel(message.from_user.id)
    else:
        await send_main_menu(message.from_user.id)

async def main():
    load_data()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import sys, asyncio
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
