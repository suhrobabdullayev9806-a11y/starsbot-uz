# ===================================================================
# handlers/states.py - FSM (state) guruhlari
# Step-by-step jarayonlar uchun foydalanuvchi holati.
# ===================================================================

from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    """Sotib olish jarayoni."""

    choose_package = State()      # paket tanlangan
    card_proof = State()          # karta to'lov tasdig'i matnini kutmoqda


class PostStarsFlow(StatesGroup):
    """Postga stars so'rovi."""

    choose_package = State()      # stars miqdori tanlanmoqda
    custom_amount = State()       # qo'lda kiritilgan miqdor kutmoqda
    wait_link = State()           # post havolasi kutmoqda
    confirm = State()             # xulosa ko'rsatilgan, tasdiq/bekor kutmoqda


class GiftFlow(StatesGroup):
    """Gift jarayoni."""

    wait_phone = State()          # telefon raqam kutmoqda


class TopupFlow(StatesGroup):
    """Hisobni so'mda to'ldirish."""

    wait_sum = State()            # so'm miqdori kutmoqda
    wait_proof = State()          # (eski) karta to'lov tasdig'i
    wait_txid = State()           # avto-to'lov: tranzaksiya ID kutmoqda


class AdminFlow(StatesGroup):
    """Admin sozlamalari kiritish."""

    wait_prices = State()         # narxlar kiritilmoqda
    wait_card = State()           # karta raqami kiritilmoqda
    wait_channel = State()        # kanal kiritilmoqda
    wait_user_id = State()        # foydalanuvchi ID si kutmoqda
    wait_gift_amount = State()    # gift miqdori kutmoqda
    wait_gift_user = State()      # gift qo'shiladigan foydalanuvchi
    wait_acct_session = State()   # akkaunt session ma'lumotlari
    wait_acct_title = State()     # akkaunt nomi
    wait_acct_delete = State()    # akkaunt ID si
    wait_broadcast = State()      # reklama xabari
    wait_api_url = State()        # Stars API URL
    wait_api_key = State()        # Stars API key
    wait_acct_test = State()      # test qilinadigan akkaunt ID si
    wait_acct_phone = State()     # login orqali ulash: telefon raqam
    wait_acct_code = State()      # login orqali ulash: tasdiqlash kodi
    wait_acct_password = State()  # login orqali ulash: 2FA parol
    wait_pay_channel = State()    # to'lovlar kanali username/chat_id
    wait_pic = State()            # bosh menyu rasmi (banner)
    wait_admin_user = State()     # admin qo'shish/o'chirish uchun user ID
    wait_star_price = State()     # 1 star narxi (so'm) — Stars/buy
    wait_gift_price = State()     # 1 star narxi (so'm) — Gift
    wait_post_price = State()     # 1 star narxi (so'm) — Post
    wait_post_min_stars = State() # postga minimal stars soni
    wait_gift_name = State()      # gift katalogi: nomi kiritish
    wait_gift_narxi = State()     # gift katalogi: narxi (so'm)
    wait_gift_soni = State()      # gift katalogi: stars soni
    wait_gift_delete = State()    # gift katalogi: o'chiriladigan ID
    wait_nft_url = State()        # NFT: t.me/nft/... havolasi
    wait_nft_price = State()      # NFT: narxi (so'm)
    wait_nft_delete = State()     # NFT: o'chiriladigan ID
    wait_nft_edit_id = State()    # NFT: narxi o'zgartiriladigan ID
    wait_nft_edit_price = State() # NFT: yangi narx
