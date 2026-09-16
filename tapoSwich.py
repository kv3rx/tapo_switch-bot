import asyncio
import os
import psutil
import socket
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from tapo import ApiClient
from dotenv import load_dotenv

IS_WINDOWS = os.name == 'nt'
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_ID = int(os.getenv("ALLOWED_ID"))
TAPO_USER = os.getenv("TAPO_USER")
TAPO_PASS = os.getenv("TAPO_PASS")
TAPO_IP = os.getenv("TAPO_IP")

TARGET_PC_IP = os.getenv("TARGET_PC_IP")
TARGET_PC_USER = os.getenv("TARGET_PC_USER")
TARGET_PC_PASS = os.getenv("TARGET_PC_PASS")

ENABLE_POWER_ALARM = False

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

update_task = None
tapo_client = None
tapo_device = None
background_tasks = set()

def get_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Керування розеткою")],
            [KeyboardButton(text="Таймер ПК"), KeyboardButton(text="Статус Хабу")],
            [KeyboardButton(text="Рестарт скрипта")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

def get_socket_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔌 Увімкнути", callback_data="socket_on"),
         InlineKeyboardButton(text="❌ Вимкнути", callback_data="socket_off")]
    ])

def get_hub_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ребут Хабу", callback_data="hub_reboot")]
    ])

def get_timer_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 год", callback_data="sd_3600"),
         InlineKeyboardButton(text="1.5 год", callback_data="sd_5400"),
         InlineKeyboardButton(text="2 год", callback_data="sd_7200")],
        [InlineKeyboardButton(text="2.5 год", callback_data="sd_9000"),
         InlineKeyboardButton(text="3 год", callback_data="sd_10800"),
         InlineKeyboardButton(text="3.5 год", callback_data="sd_12600")],
        [InlineKeyboardButton(text="4 год", callback_data="sd_14400"),
         InlineKeyboardButton(text="🛑 Скасувати", callback_data="sd_abort")],
        [InlineKeyboardButton(text="❌ Закрити", callback_data="sd_cancel")]
    ])

async def init_tapo():
    global tapo_client, tapo_device
    if not tapo_client:
        try:
            tapo_client = ApiClient(TAPO_USER, TAPO_PASS)
            tapo_device = await tapo_client.p115(TAPO_IP)
        except Exception:
            tapo_client = None
            tapo_device = None

async def reset_tapo():
    global tapo_client, tapo_device
    tapo_client = None
    tapo_device = None

async def check_internet():
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, lambda: socket.create_connection(("8.8.8.8", 53), timeout=3))
        return True
    except OSError:
        return False

async def monitor_internet():
    is_online = True
    offline_start = None
    while True:
        current_status = await check_internet()
        if current_status and not is_online:
            is_online = True
            if offline_start:
                downtime = datetime.now() - offline_start
                hours, remainder = divmod(downtime.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"{int(hours)} год {int(minutes)} хв {int(seconds)} сек"
                try:
                    await bot.send_message(ALLOWED_ID, f"🌐 Інтернет з'явився! Не було: {time_str}", reply_markup=get_kb())
                except Exception:
                    pass
            offline_start = None
        elif not current_status and is_online:
            is_online = False
            offline_start = datetime.now()
        await asyncio.sleep(10)

async def monitor_power():
    while True:
        await asyncio.sleep(300)
        try:
            await init_tapo()
            if tapo_device:
                info = await tapo_device.get_device_info()
                if info.device_on:
                    usage = await tapo_device.get_energy_usage()
                    if usage.current_power < 1000:
                        await tapo_device.off()
                        await bot.send_message(ALLOWED_ID, "Комп споживає менше 1 Вт. Розетку автоматично вирубано.", reply_markup=get_kb())
        except Exception:
            await reset_tapo()

async def monitor_ac_power():
    if not ENABLE_POWER_ALARM:
        return
    last_plugged_state = None
    while True:
        await asyncio.sleep(180)
        current_battery = psutil.sensors_battery()
        if not current_battery:
            continue
        if last_plugged_state is None:
            last_plugged_state = current_battery.power_plugged
            continue
        if current_battery.power_plugged != last_plugged_state:
            last_plugged_state = current_battery.power_plugged
            if last_plugged_state:
                try:
                    await bot.send_message(ALLOWED_ID, f"Світло з'явилося. Заряд: {current_battery.percent}%", reply_markup=get_kb())
                except Exception:
                    pass
            else:
                try:
                    await bot.send_message(ALLOWED_ID, f"Світло від'їбнуло. Сиджу на акумі: {current_battery.percent}%", reply_markup=get_kb())
                except Exception:
                    pass

async def update_status_message(message: types.Message):
    global update_task
    # Надсилаємо як ВІДОКРЕМЛЕНЕ текстове повідомлення без reply_markup,
    # щоб Telegram дозволив його динамічно редагувати.
    status_msg = await message.answer("Включаємось, збираю дані...")
    last_text = "Включаємось, збираю дані..."
    
    for i in range(3):
        await asyncio.sleep(3)
        try:
            if not tapo_device:
                await init_tapo()
            
            if tapo_device:
                usage = await tapo_device.get_energy_usage()
                watts = usage.current_power / 1000
                text = f"Вмикання... Поточне живлення: {watts:.1f} Вт"
                
                # Оновлюємо текст ТІЛЬКИ якщо кількість Ват дійсно змінилася
                if text != last_text:
                    try:
                        await status_msg.edit_text(text)
                        last_text = text
                        print(f"[INFO] Оновлено в ТГ: {watts:.1f} W")
                    except Exception as e:
                        print(f"[TG ERROR] {e}")
            else:
                print("[TAPO WARN] Device is None")
        except Exception as e:
            print(f"[TAPO FETCH ERROR] Спроба {i+1}: {e}")
            await reset_tapo()
            
            text_err = f"Очікування інфи від розетки... [Спроба {i+1}/5]"
            if text_err != last_text:
                try:
                    await status_msg.edit_text(text_err)
                    last_text = text_err
                except Exception as tg_err:
                    print(f"[TG EDIT ERROR] {tg_err}")
                
    update_task = None

@dp.message(Command("start", "menu"))
async def send_menu(message: types.Message):
    if message.from_user.id != ALLOWED_ID:
        return
    await message.answer("Меню керування розеткою активовано.", reply_markup=get_kb())

@dp.message(F.text == "Керування розеткою")
async def process_socket_control(message: types.Message):
    if message.from_user.id != ALLOWED_ID:
        return
    await init_tapo()
    if not tapo_device:
        await message.answer("Розетка недоступна.", reply_markup=get_kb())
        return
    try:
        info = await tapo_device.get_device_info()
        if info.device_on:
            usage = await tapo_device.get_energy_usage()
            watts = usage.current_power / 1000
            text = f"Розетка увімкнена. Споживання: {watts:.1f} Вт"
        else:
            text = "Розетка вимкнена."
    except Exception:
        await reset_tapo()
        text = "Розетка недоступна."
    await message.answer(text, reply_markup=get_socket_inline_kb())

@dp.callback_query(F.data == "socket_on")
async def cb_socket_on(call: types.CallbackQuery):
    global update_task
    if call.from_user.id != ALLOWED_ID:
        return
    await call.answer()
    await init_tapo()
    if not tapo_device:
        await call.message.answer("Помилка ініціалізації розетки.", reply_markup=get_kb())
        return
    try:
        await tapo_device.on()
    except Exception:
        await reset_tapo()
        await call.message.answer("Розетка недоступна. Спробуй ще раз.", reply_markup=get_kb())
        return
    if update_task is None or update_task.done():
        update_task = asyncio.create_task(update_status_message(call.message))

@dp.callback_query(F.data == "socket_off")
async def cb_socket_off(call: types.CallbackQuery):
    global update_task
    if call.from_user.id != ALLOWED_ID:
        return
    await call.answer()
    await init_tapo()
    if not tapo_device:
        await call.message.answer("Розетка недоступна.", reply_markup=get_kb())
        return
    try:
        await tapo_device.off()
    except Exception:
        await reset_tapo()
        await call.message.answer("Розетка недоступна. Спробуй ще раз.", reply_markup=get_kb())
        return
    if update_task and not update_task.done():
        update_task.cancel()
        update_task = None
    await call.message.answer("Розетку жорстко вирубано.", reply_markup=get_kb())

@dp.message(F.text == "Статус Хабу")
async def process_hub_status(message: types.Message):
    if message.from_user.id != ALLOWED_ID:
        return
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    
    # Визначаємо корінь системи
    disk_path = 'C:\\' if IS_WINDOWS else '/'
    disk = psutil.disk_usage(disk_path)
    disk_label = "Диск C" if IS_WINDOWS else "Пам'ять Хабу"
    
    battery = psutil.sensors_battery()
    bat_status = "🔌 Від мережі"
    if battery:
        if not battery.power_plugged:
            bat_status = f"🔋 На батареї ({battery.percent}%)"
        else:
            bat_status = f"🔌 Заряджається ({battery.percent}%)"
            
    text = (
        f"💻 T440p Hub Status:\n"
        f"ЦП: {cpu}%\n"
        f"ОЗП: {ram.percent}% ({ram.used // (1024**3)}/{ram.total // (1024**3)} ГБ)\n"
        f"{disk_label}: {disk.free // (1024**3)} ГБ вільно\n"
        f"Живлення: {bat_status}"
    )
    await message.answer(text, reply_markup=get_hub_inline_kb())

@dp.callback_query(F.data == "hub_reboot")
async def cb_reboot_hub(call: types.CallbackQuery):
    if call.from_user.id != ALLOWED_ID:
        return
    await call.answer()
    await call.message.answer("Пішов на ребут...", reply_markup=get_kb())
    
    if IS_WINDOWS:
        os.system("shutdown /r /t 5")
    else:
        # Для Linux. Якщо бот в Докері, ця команда спрацює ТІЛЬКИ 
        # якщо прокинуто dbus хоста (-v /var/run/dbus:/var/run/dbus)
        os.system("systemctl reboot")

@dp.message(F.text == "Рестарт скрипта")
async def process_restart_script(message: types.Message):
    if message.from_user.id != ALLOWED_ID:
        return
    await message.answer("Перезапускаю пайтон-скрипт...", reply_markup=get_kb())
    os.execv(sys.executable, [sys.executable] + sys.argv)

@dp.message(F.text == "Таймер ПК")
async def process_timer_menu(message: types.Message):
    if message.from_user.id != ALLOWED_ID:
        return
    await message.answer("Обери час до вимкнення компа:", reply_markup=get_timer_kb())

@dp.callback_query(F.data.startswith("sd_"))
async def cb_shutdown(call: types.CallbackQuery):
    if call.from_user.id != ALLOWED_ID:
        return
    await call.answer()
    action = call.data.split("_")[1]
    
    if action == "cancel":
        await call.message.delete()
        return

    # Логіка СКАСУВАННЯ таймера
    if action == "abort":
        if IS_WINDOWS:
            abort_cmd = f'shutdown /a /m \\\\{TARGET_PC_IP}'
        else:
            abort_cmd = f'net rpc abortshutdown -I {TARGET_PC_IP} -U "{TARGET_PC_USER}%{TARGET_PC_PASS}"'
            
        abort_proc = await asyncio.create_subprocess_shell(abort_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await abort_proc.communicate()
        
        if abort_proc.returncode == 0:
            await call.message.edit_text("Відлік до шатдауну скасовано.")
        else:
            await call.message.edit_text("Помилка відміни. Можливо таймер не був запущений.")
        return

    # Логіка ЗАПУСКУ таймера
    seconds = int(action)
    hours = seconds / 3600
    time_display = f"{int(hours)} год" if hours.is_integer() else f"{hours} god"

    if IS_WINDOWS:
        # Авторизація для Вінди
        auth_cmd = f'net use \\\\{TARGET_PC_IP}\\IPC$ /user:"{TARGET_PC_USER}" "{TARGET_PC_PASS}"'
        auth_proc = await asyncio.create_subprocess_shell(auth_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await auth_proc.communicate()
        if auth_proc.returncode not in (0, 1219):
            await call.message.edit_text("Помилка доступу до ПК. Авторизація не пройшла.")
            return
            
        sd_cmd = f'shutdown /s /m \\\\{TARGET_PC_IP} /t {seconds} /c "Telegram Shutdown"'
    else:
        # Команда для Linux/Docker (через Samba)
        sd_cmd = f'net rpc shutdown -I {TARGET_PC_IP} -U "{TARGET_PC_USER}%{TARGET_PC_PASS}" -t {seconds} -C "Telegram Shutdown" -f'

    sd_proc = await asyncio.create_subprocess_shell(sd_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    await sd_proc.communicate()
    
    if sd_proc.returncode == 0:
        await call.message.edit_text(f"Таймер пішов. Комп вимкнеться через {time_display}.")
    else:
        await call.message.edit_text(f"Помилка запуску шатдауну (код {sd_proc.returncode}).")

async def main():
    for coro in [monitor_ac_power(), monitor_internet(), monitor_power()]:
        task = asyncio.create_task(coro)
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())