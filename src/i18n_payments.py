# ===================================================================
# i18n_payments.py - TO'LOV va OBUNA matnlari (uz / en / ru)
# i18n.py oxirida TRANSLATIONS ga qo'shiladi (eski kalitlarni yangilaydi).
# ===================================================================

TEXTS: dict[str, dict[str, str]] = {
    "uz": {
        "sub_join": "📢 Kanalga o'tish",
        "start_not_subscribed": "🔒 <b>Botdan foydalanish uchun kanalimizga obuna bo'ling</b>\n\n"
                                "📢 Kanal: @{channel}\n\n"
                                "1️⃣ «Kanalga o'tish» tugmasini bosing va obuna bo'ling\n"
                                "2️⃣ Qaytib «✅ Tekshirish» tugmasini bosing",
        "wallet_topup": "💳 <b>Hisobni to'ldirish</b>\n\n"
                        "Hisobingizga <b>so'm</b> tushiring, keyin shu pul bilan Stars, Gift yoki "
                        "postga stars xarid qilasiz.\n\n"
                        "⚡️ <b>To'liq avto-to'lov</b> — bot sizga noyob summa beradi. Aynan shu summani "
                        "o'tkazing, bank bildirishnomasi kelganda hisob avtomatik to'ladi (tranzaksiya ID shart emas).\n\n"
                        "👇 Usulni tanlang:",
        "topup_pick": "💳 <b>Hisobni to'ldirish</b>\n\n"
                      "Qancha so'm to'ldirmoqchisiz?\n"
                      "Minimal: <b>{min} so'm</b> · Maksimal: <b>{max} so'm</b>\n\n"
                      "👇 Tayyor summani tanlang yoki o'zingiz yozing:",
        "topup_sum_prompt": "✍️ <b>Summani yozing</b> (so'mda)\n\n"
                            "Masalan: <code>150000</code>\n"
                            "Minimal: <b>{min}</b> · Maksimal: <b>{max}</b>",
        "topup_sum_bad": "⚠️ Summa noto'g'ri. <b>{min}</b> dan <b>{max}</b> so'mgacha raqam yozing.",
        "topup_card_pay": "💳 <b>To'lov ma'lumotlari</b>\n\n"
                          "💵 To'lanadigan summa: <b><code>{amount}</code> so'm</b>\n\n"
                          "🏦 Karta raqami:\n<code>{card}</code>\n"
                          "👤 Karta egasi: <b>{holder}</b>\n\n"
                          "⚠️ <b>Aynan {amount} so'm</b> o'tkazing — summa farq qilsa to'lov bekor bo'ladi.\n\n"
                          "To'lagach «✅ To'ladim» tugmasini bosing va <b>tranzaksiya ID</b> sini yozing.",
        "topup_card_auto": "💳 <b>To'lov ma'lumotlari</b>\n\n"
                           "💵 Aynan o'tkaziladigan summa: <b><code>{amount}</code> so'm</b>\n\n"
                           "🏦 Karta raqami:\n<code>{card}</code>\n"
                           "👤 Karta egasi: <b>{holder}</b>\n\n"
                           "⚠️ <b>Faqat shu summani</b> o'tkazing — bank xabari shu noyob summa bo'yicha "
                           "avtomatik aniqlanadi. Summani yaxlitlamang!\n\n"
                           "⏳ To'lov {minutes} daqiqa ichida tasdiqlanadi. Tasdiqlangach bot sizga "
                           "avtomatik xabar yuboradi.",
        "topup_card_pay_noholder": "—",
        "topup_ask_txid": "🧾 <b>Tranzaksiya ID sini yuboring</b>\n\n"
                          "Summa: <b>{amount} so'm</b>\n\n"
                          "ID ni to'lov chekidan (bank ilovasidagi «Chek» / «Ref» / «ID raqami») "
                          "nusxalab yuboring.\n"
                          "Masalan: <code>4821937465</code>",
        "topup_txid_bad": "⚠️ ID noto'g'ri. U kamida 6 ta belgi bo'lib, raqam qatnashishi kerak. "
                          "Qayta yuboring yoki bekor qiling.",
        "topup_checking": "⏳ <b>To'lov tekshirilmoqda...</b>\n\n"
                          "🧾 ID: <code>{tx}</code>\n💵 Summa: <b>{amount} so'm</b>\n\n"
                          "Bank xabari kelishi 1–2 daqiqa olishi mumkin. Natijani shu yerda yuboraman.",
        "topup_ok": "✅ <b>To'lov tasdiqlandi!</b>\n\n"
                    "💵 Qo'shildi: <b>+{amount} so'm</b>\n"
                    "👛 Hisobingiz: <b>{balance} so'm</b>\n\n"
                    "Endi Stars sotib olishingiz mumkin 🎉",
        "topup_fail_not_found_timeout": "❌ <b>To'lov topilmadi — bekor qilindi</b>\n\n"
                                        "🧾 ID: <code>{tx}</code>\n💵 Summa: {amount} so'm\n\n"
                                        "Bank tomonidan bu ID bilan kirim kelmadi. ID va summani tekshirib, "
                                        "qayta urinib ko'ring. Pul o'tgan bo'lsa — adminga murojaat qiling.",
        "topup_fail_amount_mismatch": "❌ <b>Summa mos kelmadi — bekor qilindi</b>\n\n"
                                      "🧾 ID: <code>{tx}</code>\n\n"
                                      "Siz tanlagan summa ({amount} so'm) o'tkazilgan summaga teng emas. "
                                      "Qayta urinib ko'ring yoki adminga yozing.",
        "topup_fail_tx_already_used": "❌ <b>Bu tranzaksiya avval ishlatilgan</b>\n\n"
                                      "🧾 ID: <code>{tx}</code>\n\n"
                                      "Har bir to'lov faqat bir marta hisobga olinadi.",
        "topup_fail_duplicate": "⚠️ Bu ID bilan so'rov allaqachon yuborilgan.",
        "topup_fail_too_many_pending": "⚠️ Sizda tekshiruvda turgan to'lovlar ko'p. Natijani kuting.",
        "topup_fail_rate_limit": "⚠️ Juda ko'p urinish. Bir soatdan keyin qayta urinib ko'ring.",
        "topup_fail_generic": "❌ <b>To'lov tasdiqlanmadi.</b> Qayta urinib ko'ring.",
        "topup_manual_sent": "⏳ <b>So'rov adminga yuborildi</b>\n\n"
                             "🧾 ID: <code>{tx}</code>\n💵 Summa: <b>{amount} so'm</b>\n\n"
                             "Admin tekshirib, hisobingizga qo'shadi.",
        "topup_cancelled": "🚫 To'lov bekor qilindi.",
        "topup_no_card": "⚠️ To'lov kartasi hali sozlanmagan. Iltimos, admin bilan bog'laning.",
        "topup_sent_admin": "💰 <b>Hisob to'ldirish — qo'lda tekshiruv</b>\n\n"
                            "👤 {user} · <code>{uid}</code>\n"
                            "💵 Summa: <b>{amount} so'm</b>\n"
                            "🧾 Tranzaksiya ID: <code>{proof}</code>",
        "topup_api_success": "✅ <b>Hisob to'ldirildi!</b>\n\n👛 Hisobingiz: <b>{balance} so'm</b>",
        "topup_enough": "✅ <b>Balans to'ldirildi!</b>\n\n👛 Hisobingiz: <b>{balance} so'm</b>",
        "topup_btn_app": "📱 Mini-app orqali (avto)",
        "topup_btn_card": "💳 Karta orqali (avto)",
        "topup_btn_api": "🤖 Online to'lov",
        "topup_btn_other": "✍️ Boshqa summa",
        "topup_btn_paid": "✅ To'ladim",
        "topup_btn_check": "🔄 Holatni tekshirish",
        "topup_auto_busy": "⚠️ Hozir shu summa uchun barcha noyob variantlar band. Bir necha daqiqadan keyin qayta urinib ko'ring.",
        "topup_auto_wait": "⏳ Hali bank xabari kelmadi. To'lovni amalga oshirganingizdan so'ng 1–2 daqiqa kuting.",
        "topup_not_found": "⚠️ To'lov topilmadi. Qayta urinib ko'ring.",
        "topup_btn_cancel": "🚫 Bekor qilish",
        "topup_btn_retry": "🔁 Qayta urinish",
        "topup_btn_buy": "⭐ Stars sotib olish",
        "topup_btn_wallet": "👛 Hisobim",
        "topup_btn_support": "🆘 Admin",
    },
    "en": {
        "sub_join": "📢 Open channel",
        "start_not_subscribed": "🔒 <b>Please join our channel to use the bot</b>\n\n"
                                "📢 Channel: @{channel}\n\n"
                                "1️⃣ Tap “Open channel” and subscribe\n"
                                "2️⃣ Come back and tap “✅ Check”",
        "wallet_topup": "💳 <b>Top up balance</b>\n\n"
                        "Add <b>UZS</b> to your balance, then spend it on Stars, Gifts or post stars.\n\n"
                        "⚡️ <b>Fully automatic payment</b> — the bot gives you a unique amount. Transfer "
                        "exactly that amount; the bank notification credits your balance automatically "
                        "(no transaction ID needed).\n\n"
                        "👇 Choose a method:",
        "topup_pick": "💳 <b>Top up balance</b>\n\n"
                      "How much do you want to add?\n"
                      "Min: <b>{min} UZS</b> · Max: <b>{max} UZS</b>\n\n"
                      "👇 Pick an amount or type your own:",
        "topup_sum_prompt": "✍️ <b>Send the amount</b> (UZS)\n\n"
                            "Example: <code>150000</code>\nMin: <b>{min}</b> · Max: <b>{max}</b>",
        "topup_sum_bad": "⚠️ Invalid amount. Send a number from <b>{min}</b> to <b>{max}</b> UZS.",
        "topup_card_pay": "💳 <b>Payment details</b>\n\n"
                          "💵 Amount to pay: <b><code>{amount}</code> UZS</b>\n\n"
                          "🏦 Card number:\n<code>{card}</code>\n"
                          "👤 Cardholder: <b>{holder}</b>\n\n"
                          "⚠️ Transfer <b>exactly {amount} UZS</b> — a different amount will be cancelled.\n\n"
                          "After paying tap “✅ I paid” and send the <b>transaction ID</b>.",
        "topup_card_auto": "💳 <b>Payment details</b>\n\n"
                           "💵 Exact amount to transfer: <b><code>{amount}</code> UZS</b>\n\n"
                           "🏦 Card number:\n<code>{card}</code>\n"
                           "👤 Cardholder: <b>{holder}</b>\n\n"
                           "⚠️ Transfer <b>exactly this amount</b> — the bank notification is matched by "
                           "this unique amount. Do not round it!\n\n"
                           "⏳ The payment is confirmed within {minutes} minutes. The bot will message you "
                           "automatically once it is credited.",
        "topup_card_pay_noholder": "—",
        "topup_ask_txid": "🧾 <b>Send the transaction ID</b>\n\n"
                          "Amount: <b>{amount} UZS</b>\n\n"
                          "Copy it from your payment receipt (“Receipt” / “Ref” / “ID” in the bank app).\n"
                          "Example: <code>4821937465</code>",
        "topup_txid_bad": "⚠️ Invalid ID. It must be 6+ characters and contain digits. Send again or cancel.",
        "topup_checking": "⏳ <b>Checking your payment...</b>\n\n"
                          "🧾 ID: <code>{tx}</code>\n💵 Amount: <b>{amount} UZS</b>\n\n"
                          "The bank notification can take 1–2 minutes. I'll send the result here.",
        "topup_ok": "✅ <b>Payment confirmed!</b>\n\n"
                    "💵 Added: <b>+{amount} UZS</b>\n"
                    "👛 Balance: <b>{balance} UZS</b>\n\nYou can buy Stars now 🎉",
        "topup_fail_not_found_timeout": "❌ <b>Payment not found — cancelled</b>\n\n"
                                        "🧾 ID: <code>{tx}</code>\n💵 Amount: {amount} UZS\n\n"
                                        "No incoming transfer with this ID was received. Check the ID and amount "
                                        "and try again. If you paid, contact the admin.",
        "topup_fail_amount_mismatch": "❌ <b>Amount mismatch — cancelled</b>\n\n"
                                      "🧾 ID: <code>{tx}</code>\n\n"
                                      "The chosen amount ({amount} UZS) differs from the transferred amount. "
                                      "Try again or contact the admin.",
        "topup_fail_tx_already_used": "❌ <b>This transaction was already used</b>\n\n"
                                      "🧾 ID: <code>{tx}</code>\n\nEach payment is credited only once.",
        "topup_fail_duplicate": "⚠️ A request with this ID was already submitted.",
        "topup_fail_too_many_pending": "⚠️ You have many payments under review. Please wait for the result.",
        "topup_fail_rate_limit": "⚠️ Too many attempts. Try again in an hour.",
        "topup_fail_generic": "❌ <b>Payment was not confirmed.</b> Please try again.",
        "topup_manual_sent": "⏳ <b>Request sent to admin</b>\n\n"
                             "🧾 ID: <code>{tx}</code>\n💵 Amount: <b>{amount} UZS</b>\n\n"
                             "The admin will verify and credit your balance.",
        "topup_cancelled": "🚫 Payment cancelled.",
        "topup_no_card": "⚠️ The payment card is not configured yet. Please contact the admin.",
        "topup_sent_admin": "💰 <b>Top-up — manual review</b>\n\n"
                            "👤 {user} · <code>{uid}</code>\n"
                            "💵 Amount: <b>{amount} UZS</b>\n"
                            "🧾 Transaction ID: <code>{proof}</code>",
        "topup_api_success": "✅ <b>Balance topped up!</b>\n\n👛 Balance: <b>{balance} UZS</b>",
        "topup_enough": "✅ <b>Balance topped up!</b>\n\n👛 Balance: <b>{balance} UZS</b>",
        "topup_btn_app": "📱 Via Mini-App (auto)",
        "topup_btn_card": "💳 By card (auto)",
        "topup_btn_api": "🤖 Online payment",
        "topup_btn_other": "✍️ Other amount",
        "topup_btn_paid": "✅ I paid",
        "topup_btn_check": "🔄 Check status",
        "topup_auto_busy": "⚠️ All unique amounts for this value are busy right now. Please try again in a few minutes.",
        "topup_auto_wait": "⏳ No bank notification yet. Wait 1–2 minutes after making the payment.",
        "topup_not_found": "⚠️ Payment not found. Please try again.",
        "topup_btn_cancel": "🚫 Cancel",
        "topup_btn_retry": "🔁 Try again",
        "topup_btn_buy": "⭐ Buy Stars",
        "topup_btn_wallet": "👛 My balance",
        "topup_btn_support": "🆘 Admin",
    },
    "ru": {
        "sub_join": "📢 Открыть канал",
        "start_not_subscribed": "🔒 <b>Подпишитесь на канал, чтобы пользоваться ботом</b>\n\n"
                                "📢 Канал: @{channel}\n\n"
                                "1️⃣ Нажмите «Открыть канал» и подпишитесь\n"
                                "2️⃣ Вернитесь и нажмите «✅ Проверить»",
        "wallet_topup": "💳 <b>Пополнение баланса</b>\n\n"
                        "Пополните <b>сумы</b>, затем покупайте Stars, подарки или звёзды на пост.\n\n"
                        "⚡️ <b>Полностью автоматический платёж</b> — бот выдаёт уникальную сумму. "
                        "Переведите ровно её; уведомление банка зачислит деньги автоматически "
                        "(ID транзакции не нужен).\n\n"
                        "👇 Выберите способ:",
        "topup_pick": "💳 <b>Пополнение баланса</b>\n\n"
                      "Сколько хотите внести?\n"
                      "Мин: <b>{min} сум</b> · Макс: <b>{max} сум</b>\n\n"
                      "👇 Выберите сумму или введите свою:",
        "topup_sum_prompt": "✍️ <b>Отправьте сумму</b> (в сумах)\n\n"
                            "Например: <code>150000</code>\nМин: <b>{min}</b> · Макс: <b>{max}</b>",
        "topup_sum_bad": "⚠️ Неверная сумма. Отправьте число от <b>{min}</b> до <b>{max}</b> сум.",
        "topup_card_pay": "💳 <b>Реквизиты для оплаты</b>\n\n"
                          "💵 Сумма к оплате: <b><code>{amount}</code> сум</b>\n\n"
                          "🏦 Номер карты:\n<code>{card}</code>\n"
                          "👤 Владелец: <b>{holder}</b>\n\n"
                          "⚠️ Переведите <b>ровно {amount} сум</b> — при другой сумме платёж отменяется.\n\n"
                          "После оплаты нажмите «✅ Я оплатил» и отправьте <b>ID транзакции</b>.",
        "topup_card_auto": "💳 <b>Реквизиты для оплаты</b>\n\n"
                           "💵 Точная сумма к переводу: <b><code>{amount}</code> сум</b>\n\n"
                           "🏦 Номер карты:\n<code>{card}</code>\n"
                           "👤 Владелец: <b>{holder}</b>\n\n"
                           "⚠️ Переведите <b>ровно эту сумму</b> — уведомление банка сопоставляется по "
                           "уникальной сумме. Не округляйте!\n\n"
                           "⏳ Платёж подтверждается в течение {minutes} минут. После зачисления бот "
                           "пришлёт сообщение автоматически.",
        "topup_card_pay_noholder": "—",
        "topup_ask_txid": "🧾 <b>Отправьте ID транзакции</b>\n\n"
                          "Сумма: <b>{amount} сум</b>\n\n"
                          "Скопируйте его из чека в банковском приложении («Чек» / «Ref» / «ID»).\n"
                          "Например: <code>4821937465</code>",
        "topup_txid_bad": "⚠️ Неверный ID. Минимум 6 символов, должны быть цифры. Отправьте снова или отмените.",
        "topup_checking": "⏳ <b>Проверяем платёж...</b>\n\n"
                          "🧾 ID: <code>{tx}</code>\n💵 Сумма: <b>{amount} сум</b>\n\n"
                          "Уведомление банка может идти 1–2 минуты. Результат пришлю сюда.",
        "topup_ok": "✅ <b>Платёж подтверждён!</b>\n\n"
                    "💵 Зачислено: <b>+{amount} сум</b>\n"
                    "👛 Баланс: <b>{balance} сум</b>\n\nМожно покупать Stars 🎉",
        "topup_fail_not_found_timeout": "❌ <b>Платёж не найден — отменён</b>\n\n"
                                        "🧾 ID: <code>{tx}</code>\n💵 Сумма: {amount} сум\n\n"
                                        "Поступление с таким ID не получено. Проверьте ID и сумму и попробуйте "
                                        "снова. Если деньги списаны — напишите админу.",
        "topup_fail_amount_mismatch": "❌ <b>Сумма не совпала — отменено</b>\n\n"
                                      "🧾 ID: <code>{tx}</code>\n\n"
                                      "Выбранная сумма ({amount} сум) не равна переведённой. "
                                      "Попробуйте снова или напишите админу.",
        "topup_fail_tx_already_used": "❌ <b>Эта транзакция уже использована</b>\n\n"
                                      "🧾 ID: <code>{tx}</code>\n\nКаждый платёж зачисляется один раз.",
        "topup_fail_duplicate": "⚠️ Запрос с этим ID уже отправлен.",
        "topup_fail_too_many_pending": "⚠️ У вас много платежей на проверке. Дождитесь результата.",
        "topup_fail_rate_limit": "⚠️ Слишком много попыток. Повторите через час.",
        "topup_fail_generic": "❌ <b>Платёж не подтверждён.</b> Попробуйте снова.",
        "topup_manual_sent": "⏳ <b>Запрос отправлен админу</b>\n\n"
                             "🧾 ID: <code>{tx}</code>\n💵 Сумма: <b>{amount} сум</b>\n\n"
                             "Админ проверит и зачислит деньги.",
        "topup_cancelled": "🚫 Платёж отменён.",
        "topup_no_card": "⚠️ Карта для оплаты ещё не настроена. Обратитесь к админу.",
        "topup_sent_admin": "💰 <b>Пополнение — ручная проверка</b>\n\n"
                            "👤 {user} · <code>{uid}</code>\n"
                            "💵 Сумма: <b>{amount} сум</b>\n"
                            "🧾 ID транзакции: <code>{proof}</code>",
        "topup_api_success": "✅ <b>Баланс пополнен!</b>\n\n👛 Баланс: <b>{balance} сум</b>",
        "topup_enough": "✅ <b>Баланс пополнен!</b>\n\n👛 Баланс: <b>{balance} сум</b>",
        "topup_btn_app": "📱 Через Mini-App (авто)",
        "topup_btn_card": "💳 По карте (авто)",
        "topup_btn_api": "🤖 Онлайн-оплата",
        "topup_btn_other": "✍️ Другая сумма",
        "topup_btn_paid": "✅ Я оплатил",
        "topup_btn_check": "🔄 Проверить статус",
        "topup_auto_busy": "⚠️ Все уникальные суммы для этого значения заняты. Попробуйте через несколько минут.",
        "topup_auto_wait": "⏳ Уведомление банка ещё не пришло. Подождите 1–2 минуты после оплаты.",
        "topup_not_found": "⚠️ Платёж не найден. Попробуйте снова.",
        "topup_btn_cancel": "🚫 Отмена",
        "topup_btn_retry": "🔁 Повторить",
        "topup_btn_buy": "⭐ Купить Stars",
        "topup_btn_wallet": "👛 Мой баланс",
        "topup_btn_support": "🆘 Админ",
    },
}
