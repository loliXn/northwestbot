from __future__ import annotations

import re
from datetime import date, datetime
from typing import Dict, Iterable, Sequence
from urllib.parse import urlsplit

from aiogram.types import (
    CopyTextButton,
    DisabledButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.core.constants import PAYMENT_MODE_FIXED, PAYMENT_MODE_SPLIT
from app.ui.states import (
    CycleAction,
    DueDateChangeAction,
    MemberAction,
    ParticipantAction,
    PaymentDestinationAction,
    ReminderAction,
    ReminderSendAction,
    SubscriptionAction,
    TestListAction,
    TestPaidAction,
    TestSendAction,
    TopUpAction,
)

# A maximal run of digits with single spaces or dashes between them. The run is
# taken whole (no backtracking into a shorter tail) and then filtered by digit
# count, so a grouped 20-digit bank account never yields a 16-digit "card".
DIGIT_RUN_RE = re.compile(r"(?<!\w)\d(?:[ \-]?\d)*(?![ \-]?\d)(?!\w)")
CARD_NUMBER_MIN_DIGITS = 13
CARD_NUMBER_MAX_DIGITS = 19
# An IBAN-like token (compact "DE89370400440532013000" or grouped "DE89 3704 0044 ...").
IBAN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}(?![A-Z0-9])", re.IGNORECASE)
COPY_TEXT_MAX_LEN = 256
PAYMENT_LINK_WEB_SCHEMES = {"http", "https"}
PAYMENT_LINK_TG_SCHEME = "tg"


def extract_copyable_requisite(details: str) -> tuple[str, str] | None:
    """Pick the one thing worth a copy button out of free-form payment details.

    Returns ``(button_label, text_to_copy)``: the first card-like number (digits
    only) wins; otherwise, when an IBAN-like token is present, the whole
    details text trimmed to Telegram's copy limit. ``None`` means no button.
    """
    text = (details or "").strip()
    if not text:
        return None
    iban_spans = [match.span() for match in IBAN_RE.finditer(text)]
    # Blank out IBANs before the card search so a grouped IBAN's digit tail is
    # not mistaken for a card number.
    masked = list(text)
    for start, end in iban_spans:
        masked[start:end] = " " * (end - start)
    masked_text = "".join(masked)
    for match in DIGIT_RUN_RE.finditer(masked_text):
        digits = re.sub(r"\D", "", match.group(0))
        if CARD_NUMBER_MIN_DIGITS <= len(digits) <= CARD_NUMBER_MAX_DIGITS:
            return f"📋 Copy card number ···{digits[-4:]}", digits
    if iban_spans:
        return "📋 Copy details", text[:COPY_TEXT_MAX_LEN]
    return None


def is_openable_payment_link(link: str) -> bool:
    """True when the link is safe to put into an inline ``url=`` button.

    Telegram rejects the whole message (BUTTON_URL_INVALID) for a malformed
    button URL, so anything doubtful stays a plain text line instead.
    """
    link = (link or "").strip()
    if not link or any(ch.isspace() or ord(ch) < 32 for ch in link):
        return False
    parts = urlsplit(link)
    scheme = parts.scheme.lower()
    if scheme in PAYMENT_LINK_WEB_SCHEMES:
        return bool(parts.netloc)
    if scheme == PAYMENT_LINK_TG_SCHEME:
        return bool(parts.netloc or parts.path)
    return False


def payment_requisite_rows(payment_details: str = "", payment_link: str = "") -> list[list[InlineKeyboardButton]]:
    """Rows that go above the "Paid" buttons: copy-requisite and open-link, when available."""
    rows: list[list[InlineKeyboardButton]] = []
    requisite = extract_copyable_requisite(payment_details)
    if requisite is not None:
        label, copy_value = requisite
        rows.append([InlineKeyboardButton(text=label, copy_text=CopyTextButton(text=copy_value))])
    link = (payment_link or "").strip()
    if is_openable_payment_link(link):
        rows.append([InlineKeyboardButton(text="🔗 Open payment link", url=link)])
    return rows


COMMON_TIMEZONES = (
    "Europe/Moscow",
    "Europe/London",
    "Europe/Berlin",
    "Asia/Dubai",
    "Asia/Almaty",
    "Asia/Tokyo",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "UTC",
)


def _format_cycle_button_label(due_value: str) -> str:
    try:
        return datetime.strptime(due_value, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return due_value


# Button language, shared by every screen (Bot API button styles):
#   primary (blue)  - the single main action of a screen;
#   success (green) - a positive confirmation (Paid, Approve) or the option
#                     that is currently selected in a picker;
#   danger  (red)   - anything that deletes, rejects, clears or cancels;
#   navigation (Back, Close, pagination) stays neutral.
# Clients that ignore styles still see the ✅ and 🗑 markers in the labels.
STYLE_PRIMARY = "primary"
STYLE_SUCCESS = "success"
STYLE_DANGER = "danger"
SELECTED_MARK = "✅ "
BACK_TEXT = "⬅️ Back"
CLOSE_TEXT = "✖️ Close"
CLOSE_CALLBACK = "menu:close"
OTHER_TEXT = "✏️ Other"
DEFAULT_TEXT = "Default"
DELETE_TEXT = "🗑 Delete"
DELETE_CONFIRM_TEXT = "🗑 Yes, delete"
MAIN_MENU_PLACEHOLDER = "Choose a section"
TIME_PRESETS = ("09:00", "12:00", "16:00", "20:00")
CURRENCY_PRESETS = ("USD", "EUR", "RUB")


def close_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text=CLOSE_TEXT, callback_data=CLOSE_CALLBACK)


def nav_row(back_callback: str | None = None) -> list[InlineKeyboardButton]:
    """The bottom row of a screen: ⬅️ Back when it has a parent, and ✖️ Close."""
    if back_callback is None:
        return [close_button()]
    return [InlineKeyboardButton(text=BACK_TEXT, callback_data=back_callback), close_button()]


def choice_button(text: str, callback_data: str, *, selected: bool) -> InlineKeyboardButton:
    """An option of a picker: the selected one is ticked and green."""
    if selected:
        return InlineKeyboardButton(
            text=f"{SELECTED_MARK}{text}",
            callback_data=callback_data,
            style=STYLE_SUCCESS,
        )
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def danger_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data, style=STYLE_DANGER)


def grid(buttons: Sequence[InlineKeyboardButton], columns: int = 2) -> list[list[InlineKeyboardButton]]:
    """Lay buttons out in rows of ``columns``; a lone last button spans its row."""
    return [list(buttons[index : index + columns]) for index in range(0, len(buttons), columns)]


def _markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _menu_keyboard(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    """The main menu under the input field: always available, never hidden behind the keyboard icon."""
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=MAIN_MENU_PLACEHOLDER,
    )


def admin_reply_keyboard() -> ReplyKeyboardMarkup:
    return _menu_keyboard(
        [
            [KeyboardButton(text="👥 Users"), KeyboardButton(text="📋 Subscriptions", style=STYLE_PRIMARY)],
            [KeyboardButton(text="💳 Payment"), KeyboardButton(text="📊 Reports")],
            [KeyboardButton(text="⚙️ Settings")],
        ]
    )


def public_reply_keyboard() -> ReplyKeyboardMarkup:
    return _menu_keyboard(
        [
            [KeyboardButton(text="👤 Account", style=STYLE_PRIMARY), KeyboardButton(text="📋 Subscriptions")],
            [KeyboardButton(text="📊 Reports"), KeyboardButton(text="⚙️ Settings")],
        ]
    )


def dialog_cancel_inline_button() -> InlineKeyboardButton:
    return danger_button("Cancel", "dialog:cancel")


def _prompt_markup(rows: list[list[InlineKeyboardButton]], force_reply: bool) -> InlineKeyboardMarkup:
    """Markup for a text prompt.

    ``force_reply=True`` opens the reply box on the client, so it is only valid
    on a freshly sent prompt (``message.answer``); pass ``False`` when the
    keyboard is attached through ``edit_text``/``edit_reply_markup``.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=rows,
        force_reply=True if force_reply else None,
    )


def dialog_cancel_inline_keyboard(force_reply: bool = True) -> InlineKeyboardMarkup:
    """Cancel-only keyboard for text prompts."""
    return _prompt_markup([[dialog_cancel_inline_button()]], force_reply)


def pagination_row(
    page: int,
    total_pages: int,
    *,
    previous_callback: str,
    next_callback: str,
) -> list[InlineKeyboardButton]:
    """A stable three-button row: ◀️, "n / N" counter, ▶️.

    Arrows that cannot move further are rendered disabled instead of being
    dropped, so the row keeps its shape and the counter never jumps.
    """
    if page > 1:
        previous_button = InlineKeyboardButton(text="◀️", callback_data=previous_callback)
    else:
        previous_button = InlineKeyboardButton(text="◀️", disabled=DisabledButton())
    if page < total_pages:
        next_button = InlineKeyboardButton(text="▶️", callback_data=next_callback)
    else:
        next_button = InlineKeyboardButton(text="▶️", disabled=DisabledButton())
    return [
        previous_button,
        InlineKeyboardButton(text=f"{page} / {total_pages}", disabled=DisabledButton()),
        next_button,
    ]


def build_subscription_list_keyboard(subs: Sequence[Dict[str, object]]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="➕ New subscription",
                callback_data=SubscriptionAction(action="create", subscription_id=0).pack(),
                style=STYLE_PRIMARY,
            )
        ]
    ]
    for sub in subs:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{sub['name']} ({sub['amount']:.2f} {sub['currency']})",
                    callback_data=SubscriptionAction(action="open", subscription_id=sub["id"]).pack(),
                )
            ]
        )
    return _markup(rows)


def build_members_list_keyboard(
    friends: Sequence[Dict[str, object]],
    *,
    page: int = 1,
    total_pages: int = 1,
    total_users: int = 0,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="➕ Add user",
                callback_data=MemberAction(action="add", friend_id=0).pack(),
                style=STYLE_PRIMARY,
            )
        ]
    ]
    friend_buttons = [
        InlineKeyboardButton(
            text=str(friend["full_name"]),
            callback_data=MemberAction(action="open", friend_id=int(friend["id"])).pack(),
        )
        for friend in friends
    ]
    rows.extend(grid(friend_buttons, 2 if total_users > 4 else 1))
    if total_pages > 1:
        rows.append(
            pagination_row(
                page,
                total_pages,
                previous_callback=MemberAction(action="page", friend_id=page - 1).pack(),
                next_callback=MemberAction(action="page", friend_id=page + 1).pack(),
            )
        )
    rows.append(nav_row())
    return _markup(rows)


def member_detail_keyboard(friend_id: int, *, is_pending: bool = False) -> InlineKeyboardMarkup:
    def action(name: str) -> str:
        return MemberAction(action=name, friend_id=friend_id).pack()

    rows: list[list[InlineKeyboardButton]] = []
    if is_pending:
        # A user who has not linked Telegram yet needs the link before anything else.
        rows.append([InlineKeyboardButton(text="🔗 Auth link", callback_data=action("invite"), style=STYLE_PRIMARY)])
    rows.extend(
        grid(
            [
                InlineKeyboardButton(text="✏️ Rename", callback_data=action("rename")),
                InlineKeyboardButton(text="📊 Reports", callback_data=action("report")),
                InlineKeyboardButton(text="💰 Balance", callback_data=action("balance")),
                InlineKeyboardButton(text="💳 Payment method", callback_data=action("payment_destination")),
            ]
        )
    )
    rows.append([danger_button(DELETE_TEXT, action("delete"))])
    rows.append(nav_row(action("back")))
    return _markup(rows)


def member_balance_keyboard(friend_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(
                    text="✏️ Set",
                    callback_data=MemberAction(action="balance_set", friend_id=friend_id).pack(),
                    style=STYLE_PRIMARY,
                ),
                InlineKeyboardButton(
                    text="💱 Currency",
                    callback_data=MemberAction(action="balance_currency", friend_id=friend_id).pack(),
                ),
            ],
            nav_row(MemberAction(action="open", friend_id=friend_id).pack()),
        ]
    )


def member_balance_currency_keyboard(
    friend_id: int,
    current_currency: str,
) -> InlineKeyboardMarkup:
    normalized_current = current_currency.upper()
    return _markup(
        [
            [
                choice_button(
                    code,
                    f"member_balance_currency:{friend_id}:{code}",
                    selected=code == normalized_current,
                )
                for code in CURRENCY_PRESETS
            ],
            [
                InlineKeyboardButton(
                    text=OTHER_TEXT,
                    callback_data=MemberAction(action="balance_currency_other", friend_id=friend_id).pack(),
                )
            ],
            nav_row(MemberAction(action="balance", friend_id=friend_id).pack()),
        ]
    )


def member_delete_confirm_keyboard(friend_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [danger_button(DELETE_CONFIRM_TEXT, MemberAction(action="confirm_delete", friend_id=friend_id).pack())],
            nav_row(MemberAction(action="open", friend_id=friend_id).pack()),
        ]
    )


def member_report_keyboard(friend_id: int) -> InlineKeyboardMarkup:
    return _markup([nav_row(MemberAction(action="open", friend_id=friend_id).pack())])


def _find_destination(
    destinations: Sequence[Dict[str, object]],
    destination_id: int,
) -> Dict[str, object] | None:
    return next(
        (item for item in destinations if int(item.get("id") or 0) == destination_id),
        None,
    )


def member_payment_destination_keyboard(
    friend_id: int,
    destinations: Sequence[Dict[str, object]],
    assigned_destination_id: int | None,
    default_destination_id: int | None,
) -> InlineKeyboardMarkup:
    default_target = _find_destination(destinations, default_destination_id) if default_destination_id else None
    default_label = f"Default ({default_target['title']})" if default_target else DEFAULT_TEXT
    rows = [
        [
            choice_button(
                default_label,
                f"member_payment_destination_default:{friend_id}",
                selected=assigned_destination_id is None,
            )
        ]
    ]
    for item in destinations:
        destination_id = int(item["id"])
        rows.append(
            [
                choice_button(
                    f"{item['title']} ({item['currency']})",
                    f"member_payment_destination:{friend_id}:{destination_id}",
                    selected=assigned_destination_id == destination_id,
                )
            ]
        )
    rows.append(nav_row(MemberAction(action="open", friend_id=friend_id).pack()))
    return _markup(rows)


def payment_destinations_keyboard(
    destinations: Sequence[Dict[str, object]],
    default_destination_id: int | None,
    pending_count: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="➕ Add payment method",
                callback_data=PaymentDestinationAction(action="create", destination_id=0).pack(),
                style=STYLE_PRIMARY,
            )
        ],
        [
            InlineKeyboardButton(
                text=f"📥 Pending top-ups ({pending_count})",
                callback_data=TopUpAction(action="admin_list", request_id=0).pack(),
            )
        ],
    ]
    for item in destinations:
        destination_id = int(item["id"])
        title = str(item.get("title") or f"Method {destination_id}")
        currency = str(item.get("currency") or "RUB")
        # ⭐ marks the default method, as on its own card and in the top-up picker.
        prefix = "⭐ " if default_destination_id == destination_id else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{title} ({currency})",
                    callback_data=PaymentDestinationAction(action="open", destination_id=destination_id).pack(),
                )
            ]
        )
    rows.append(nav_row())
    return _markup(rows)


def payment_destination_detail_keyboard(
    destination_id: int,
    *,
    is_default: bool,
) -> InlineKeyboardMarkup:
    def action(name: str) -> str:
        return PaymentDestinationAction(action=name, destination_id=destination_id).pack()

    rows = grid(
        [
            InlineKeyboardButton(text="✏️ Title", callback_data=action("edit_title")),
            InlineKeyboardButton(text="💱 Currency", callback_data=action("edit_currency")),
            InlineKeyboardButton(text="📝 Details", callback_data=action("edit_details")),
            InlineKeyboardButton(text="🔗 Link", callback_data=action("edit_link")),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⭐ Default" if is_default else "☆ Set default",
                callback_data=action("set_default"),
                style=STYLE_SUCCESS if is_default else None,
            )
        ]
    )
    rows.append([danger_button(DELETE_TEXT, action("delete"))])
    rows.append(nav_row(PaymentDestinationAction(action="menu", destination_id=0).pack()))
    return _markup(rows)


def payment_destination_delete_keyboard(destination_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                danger_button(
                    DELETE_CONFIRM_TEXT,
                    PaymentDestinationAction(action="confirm_delete", destination_id=destination_id).pack(),
                )
            ],
            nav_row(PaymentDestinationAction(action="open", destination_id=destination_id).pack()),
        ]
    )


def topup_request_submit_keyboard(
    request_id: int,
    payment_details: str = "",
    payment_link: str = "",
) -> InlineKeyboardMarkup:
    rows = payment_requisite_rows(payment_details, payment_link)
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ I paid",
                callback_data=TopUpAction(action="submit", request_id=request_id).pack(),
                style=STYLE_SUCCESS,
            )
        ]
    )
    rows.append(nav_row())
    return _markup(rows)


def topup_pending_requests_keyboard(requests: Sequence[Dict[str, object]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in requests:
        request_id = int(item["id"])
        title = str(item.get("full_name") or f"User {item.get('friend_id')}")
        amount = float(item.get("amount") or 0.0)
        currency = str(item.get("currency") or "RUB")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{title} · {amount:.2f} {currency}",
                    callback_data=TopUpAction(action="admin_open", request_id=request_id).pack(),
                )
            ]
        )
    rows.append(nav_row(PaymentDestinationAction(action="menu", destination_id=0).pack()))
    return _markup(rows)


def topup_request_review_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=TopUpAction(action="approve", request_id=request_id).pack(),
                    style=STYLE_SUCCESS,
                ),
                danger_button("✖️ Reject", TopUpAction(action="reject", request_id=request_id).pack()),
            ],
            nav_row(TopUpAction(action="admin_list", request_id=0).pack()),
        ]
    )


def topup_destination_keyboard(
    destinations: Sequence[Dict[str, object]],
    default_destination_id: int | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in destinations:
        destination_id = int(item["id"])
        prefix = "⭐ " if default_destination_id == destination_id else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{item['title']} ({item['currency']})",
                    callback_data=f"topup_destination:{destination_id}",
                )
            ]
        )
    rows.append(nav_row())
    return _markup(rows)


def public_account_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(
                    text="➕ Top up",
                    callback_data=TopUpAction(action="start", request_id=0).pack(),
                    style=STYLE_PRIMARY,
                )
            ],
            [InlineKeyboardButton(text="✏️ Rename", callback_data="public_account:rename")],
            nav_row(),
        ]
    )


def build_public_subscription_list_keyboard(subs: Sequence[Dict[str, object]]) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(
                    text=str(sub["name"]),
                    callback_data=SubscriptionAction(action="open_public", subscription_id=sub["id"]).pack(),
                )
            ]
            for sub in subs
        ]
    )


def _subscription_callback(subscription_id: int, action: str) -> str:
    return SubscriptionAction(action=action, subscription_id=subscription_id).pack()


def subscription_detail_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    def button(text: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=_subscription_callback(subscription_id, action))

    return _markup(
        [
            [button("💰 Pricing & schedule", "pricing")],
            [button("👥 Participants", "participants"), button("🔔 Reminders", "reminders")],
            [button("💳 Payment", "paymentinfo"), button("📊 Reports", "more")],
            [button("✏️ Rename", "rename")],
            nav_row(_subscription_callback(subscription_id, "back")),
        ]
    )


def public_subscription_detail_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    def button(text: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=_subscription_callback(subscription_id, action))

    return _markup(
        [
            [button("💱 My currency", "public_currency"), button("⏰ My reminder time", "public_remindertime")],
            [button("📊 Reports", "public_report")],
            nav_row(_subscription_callback(subscription_id, "public_back")),
        ]
    )


def build_back_keyboard(subscription_id: int, back_action: str) -> InlineKeyboardMarkup:
    return _markup([nav_row(_subscription_callback(subscription_id, back_action))])


def subscription_report_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return build_back_keyboard(subscription_id, "more")


def subscription_open_cycles_keyboard(
    subscription_id: int,
    due_dates: Sequence[str] = (),
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"📅 {_format_cycle_button_label(due_value)}",
                callback_data=CycleAction(
                    action="open",
                    subscription_id=subscription_id,
                    due_date=due_value,
                ).pack(),
            )
        ]
        for due_value in due_dates
    ]
    rows.append(nav_row(_subscription_callback(subscription_id, "more")))
    return _markup(rows)


def subscription_cycle_actions_keyboard(subscription_id: int, due_value: str) -> InlineKeyboardMarkup:
    def action(name: str) -> str:
        return CycleAction(action=name, subscription_id=subscription_id, due_date=due_value).pack()

    return _markup(
        [
            [
                InlineKeyboardButton(text="♻️ Recreate cycle", callback_data=action("recreate")),
                InlineKeyboardButton(text="✅ Force close", callback_data=action("force_close")),
            ],
            nav_row(_subscription_callback(subscription_id, "cycles")),
        ]
    )


def public_subscription_report_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return build_back_keyboard(subscription_id, "open_public")


def reminder_settings_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    def button(text: str, action: str, style: str | None = None) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text,
            callback_data=_subscription_callback(subscription_id, action),
            style=style,
        )

    return _markup(
        [
            [button("⏰ Reminder time", "remindertime"), button("🔔 Reminder days", "reminderdays")],
            [button("📣 Post-due alerts", "reminderloop")],
            [button("📬 Send reminders now", "reminders_send", STYLE_PRIMARY)],
            nav_row(_subscription_callback(subscription_id, "open")),
        ]
    )


def participants_settings_keyboard(
    subscription_id: int,
    current_mode: str,
) -> InlineKeyboardMarkup:
    normalized_mode = (current_mode or PAYMENT_MODE_SPLIT).strip().lower()
    rows = [
        [
            InlineKeyboardButton(
                text="👥 Manage users",
                callback_data=_subscription_callback(subscription_id, "participants_manage"),
            )
        ],
        [
            choice_button(
                "Split by shares",
                f"sub_payment_mode:{subscription_id}:{PAYMENT_MODE_SPLIT}",
                selected=normalized_mode == PAYMENT_MODE_SPLIT,
            ),
            choice_button(
                "Fixed per user",
                f"sub_payment_mode:{subscription_id}:{PAYMENT_MODE_FIXED}",
                selected=normalized_mode == PAYMENT_MODE_FIXED,
            ),
        ],
    ]
    if normalized_mode == PAYMENT_MODE_FIXED:
        rows.append(
            [
                InlineKeyboardButton(
                    text="💵 Amount per user",
                    callback_data=_subscription_callback(subscription_id, "useramounts"),
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="➗ Shares & split",
                    callback_data=_subscription_callback(subscription_id, "share"),
                )
            ]
        )
    rows.append(nav_row(_subscription_callback(subscription_id, "open")))
    return _markup(rows)


def subscription_more_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(
                    text="📊 Subscription report",
                    callback_data=_subscription_callback(subscription_id, "report"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗂 Open cycles",
                    callback_data=_subscription_callback(subscription_id, "cycles"),
                )
            ],
            [danger_button(DELETE_TEXT, _subscription_callback(subscription_id, "delete"))],
            nav_row(_subscription_callback(subscription_id, "open")),
        ]
    )


def subscription_delete_confirm_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [danger_button(DELETE_CONFIRM_TEXT, _subscription_callback(subscription_id, "confirm_delete"))],
            nav_row(_subscription_callback(subscription_id, "more")),
        ]
    )


def subscription_payment_info_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(
                    text="💳 Payment method",
                    callback_data=_subscription_callback(subscription_id, "paymentmethod"),
                ),
                InlineKeyboardButton(
                    text="📝 Comment",
                    callback_data=_subscription_callback(subscription_id, "comment"),
                ),
            ],
            nav_row(_subscription_callback(subscription_id, "open")),
        ]
    )


def subscription_payment_destination_keyboard(
    subscription_id: int,
    destinations: Sequence[Dict[str, object]],
    selected_destination_id: int | None,
    default_destination_id: int | None,
) -> InlineKeyboardMarkup:
    default_label = DEFAULT_TEXT
    if default_destination_id is not None:
        default_target = _find_destination(destinations, default_destination_id)
        if default_target:
            default_label = f"Default ({default_target['title']} · {default_target['currency']})"
    rows = [
        [
            choice_button(
                default_label,
                f"sub_payment_destination:{subscription_id}:default",
                selected=selected_destination_id is None,
            )
        ]
    ]
    for item in destinations:
        destination_id = int(item["id"])
        rows.append(
            [
                choice_button(
                    f"{item['title']} ({item['currency']})",
                    f"sub_payment_destination:{subscription_id}:{destination_id}",
                    selected=selected_destination_id == destination_id,
                )
            ]
        )
    rows.append(nav_row(_subscription_callback(subscription_id, "paymentinfo")))
    return _markup(rows)


def _preset_picker(
    preset_buttons: Sequence[InlineKeyboardButton],
    *,
    columns: int,
    other_callback: str,
    default_button: InlineKeyboardButton | None,
    back_callback: str,
) -> InlineKeyboardMarkup:
    """Shared layout of the time, timezone and currency pickers.

    Presets in a grid, then "✏️ Other" (typed value) and, where the setting can
    fall back to a default, "Default" on the same row, then navigation.
    """
    rows = grid(preset_buttons, columns)
    extra_row = [InlineKeyboardButton(text=OTHER_TEXT, callback_data=other_callback)]
    if default_button is not None:
        extra_row.append(default_button)
    rows.append(extra_row)
    rows.append(nav_row(back_callback))
    return _markup(rows)


def _time_preset_buttons(
    callback_prefix: str,
    current: str,
    *,
    default_active: bool = False,
) -> list[InlineKeyboardButton]:
    return [
        choice_button(
            time_value,
            f"{callback_prefix}:{time_value}",
            selected=time_value == current and not default_active,
        )
        for time_value in TIME_PRESETS
    ]


def subscription_reminder_time_keyboard(
    subscription_id: int,
    current_time: str,
    default_time: str,
) -> InlineKeyboardMarkup:
    normalized_current = current_time.strip()
    default_active = normalized_current == default_time.strip()
    return _preset_picker(
        _time_preset_buttons(f"sub_remindertime:{subscription_id}", normalized_current, default_active=default_active),
        columns=2,
        other_callback=f"sub_remindertime_other:{subscription_id}",
        default_button=choice_button(
            DEFAULT_TEXT,
            _subscription_callback(subscription_id, "remindertime_default"),
            selected=default_active,
        ),
        back_callback=_subscription_callback(subscription_id, "open"),
    )


def public_subscription_reminder_time_keyboard(
    subscription_id: int,
    current_time: str,
    default_time: str,
) -> InlineKeyboardMarkup:
    normalized_current = current_time.strip()
    default_active = normalized_current == default_time.strip()
    return _preset_picker(
        _time_preset_buttons(
            f"public_sub_remindertime:{subscription_id}",
            normalized_current,
            default_active=default_active,
        ),
        columns=2,
        other_callback=f"public_sub_remindertime_other:{subscription_id}",
        default_button=choice_button(
            DEFAULT_TEXT,
            _subscription_callback(subscription_id, "public_remindertime_default"),
            selected=default_active,
        ),
        back_callback=_subscription_callback(subscription_id, "open_public"),
    )


def reminder_send_targets_keyboard(
    subscription_id: int,
    participants: Sequence[Dict[str, object]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="📬 All",
                callback_data=ReminderSendAction(subscription_id=subscription_id, telegram_id=0).pack(),
                style=STYLE_PRIMARY,
            )
        ]
    ]
    for person in participants:
        rows.append(
            [
                InlineKeyboardButton(
                    text=str(person.get("full_name") or "Unknown"),
                    callback_data=ReminderSendAction(
                        subscription_id=subscription_id,
                        telegram_id=int(person["telegram_id"]),
                    ).pack(),
                )
            ]
        )
    rows.append(nav_row(_subscription_callback(subscription_id, "reminders")))
    return _markup(rows)


def settings_tests_keyboard(
    friends: Sequence[Dict[str, object]],
    *,
    page: int = 1,
    total_pages: int = 1,
    total_users: int = 0,
) -> InlineKeyboardMarkup:
    friend_buttons = [
        InlineKeyboardButton(
            text=str(friend.get("full_name") or "Unknown"),
            callback_data=TestSendAction(telegram_id=int(friend["telegram_id"])).pack(),
        )
        for friend in friends
    ]
    rows = grid(friend_buttons, 2 if total_users > 4 else 1)
    if total_pages > 1:
        rows.append(
            pagination_row(
                page,
                total_pages,
                previous_callback=TestListAction(action="page", page=page - 1).pack(),
                next_callback=TestListAction(action="page", page=page + 1).pack(),
            )
        )
    rows.append(nav_row("settings:tests"))
    return _markup(rows)


def tests_menu_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="📬 Send test reminders", callback_data="tests:send", style=STYLE_PRIMARY)],
            nav_row("settings:menu"),
        ]
    )


def pricing_settings_keyboard(subscription_id: int) -> InlineKeyboardMarkup:
    def button(text: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=_subscription_callback(subscription_id, action))

    return _markup(
        [
            [button("💰 Amount", "amount"), button("💱 Currency", "currency")],
            [button("📅 Next charge", "duedate"), button("🔁 Period", "period")],
            [button("🌐 Convert currency", "basecurrency")],
            nav_row(_subscription_callback(subscription_id, "open")),
        ]
    )


def subscription_user_amounts_keyboard(
    subscription_id: int,
    participants: Sequence[Dict[str, object]],
    currency: str,
    subscription_amount: float,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for person in participants:
        name = str(person.get("full_name") or "Unknown")
        weight = int(person.get("share_weight") or 1)
        fixed_amount = person.get("fixed_amount")
        try:
            base_value = float(fixed_amount) if fixed_amount is not None else float(subscription_amount)
        except (TypeError, ValueError):
            base_value = float(subscription_amount)
        if weight > 1:
            amount_text = f"{base_value:.2f} (x{weight}) {currency.upper()}"
        else:
            amount_text = f"{base_value:.2f} {currency.upper()}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{name} — {amount_text}",
                    callback_data=f"sub_user_amount:{subscription_id}:{int(person['id'])}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✏️ Set all",
                callback_data=f"sub_user_amount_all:{subscription_id}",
                style=STYLE_PRIMARY,
            )
        ]
    )
    rows.append(nav_row(_subscription_callback(subscription_id, "participants")))
    return _markup(rows)


def user_amount_clear_keyboard(
    subscription_id: int,
    friend_id: int,
    *,
    force_reply: bool = True,
) -> InlineKeyboardMarkup:
    return _prompt_markup(
        [
            [danger_button("Clear", f"sub_user_amount_clear:{subscription_id}:{friend_id}")],
            [dialog_cancel_inline_button()],
        ],
        force_reply,
    )


def subscription_base_currency_keyboard(
    subscription_id: int,
    current_currency: str,
) -> InlineKeyboardMarkup:
    normalized_current = current_currency.upper()
    return _preset_picker(
        [
            choice_button(code, f"sub_base_currency:{subscription_id}:{code}", selected=code == normalized_current)
            for code in CURRENCY_PRESETS
        ],
        columns=3,
        other_callback=_subscription_callback(subscription_id, "basecurrency_other"),
        default_button=None,
        back_callback=_subscription_callback(subscription_id, "pricing"),
    )


def build_participants_keyboard(friends: Sequence[Dict[str, object]], subscription_id: int) -> InlineKeyboardMarkup:
    rows = []
    for friend in friends:
        toggle_callback = ParticipantAction(
            action="toggle",
            subscription_id=subscription_id,
            friend_id=friend["id"],
        ).pack()
        if friend["is_member"]:
            weight_value = int(friend.get("share_weight") or 1)
            weight_callback = ParticipantAction(
                action="weight",
                subscription_id=subscription_id,
                friend_id=friend["id"],
            ).pack()
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ {friend['full_name']}",
                        callback_data=toggle_callback,
                        style=STYLE_SUCCESS,
                    ),
                    InlineKeyboardButton(text=f"x{weight_value}", callback_data=weight_callback),
                ]
            )
        else:
            rows.append([InlineKeyboardButton(text=f"☐ {friend['full_name']}", callback_data=toggle_callback)])
    rows.append(nav_row(_subscription_callback(subscription_id, "participants")))
    return _markup(rows)


def build_currency_keyboard(options: Iterable[str], *, force_reply: bool = True) -> InlineKeyboardMarkup:
    rows = grid(
        [InlineKeyboardButton(text=code.upper(), callback_data=f"currency:{code.upper()}") for code in options],
        3,
    )
    rows.append([dialog_cancel_inline_button()])
    return _prompt_markup(rows, force_reply)


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(text="⏰ Base time", callback_data="settings:time"),
                InlineKeyboardButton(text="🌍 Timezone", callback_data="settings:timezone"),
            ],
            [
                InlineKeyboardButton(text="🔢 Rounding", callback_data="settings:rounding"),
                InlineKeyboardButton(text="🔔 Notifications", callback_data="settings:notifications"),
            ],
            [InlineKeyboardButton(text="🧪 Tests", callback_data="settings:tests")],
            nav_row(),
        ]
    )


def settings_time_keyboard(current_time: str) -> InlineKeyboardMarkup:
    return _preset_picker(
        _time_preset_buttons("settings_time", current_time),
        columns=2,
        other_callback="settings:time_other",
        default_button=None,
        back_callback="settings:menu",
    )


def settings_timezone_keyboard(current_timezone: str) -> InlineKeyboardMarkup:
    return _preset_picker(
        [
            choice_button(zone, f"settings_timezone:{zone}", selected=zone == current_timezone)
            for zone in COMMON_TIMEZONES
        ],
        columns=2,
        other_callback="settings:timezone_other",
        default_button=None,
        back_callback="settings:menu",
    )


def public_settings_keyboard(
    current_time: str,
    current_timezone: str,
) -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(text="⏰ Reminder time", callback_data="public_settings:time"),
                InlineKeyboardButton(text="🌍 Timezone", callback_data="public_settings:timezone"),
            ],
            nav_row(),
        ]
    )


def public_subscription_currency_keyboard(
    subscription_id: int,
    current_currency: str,
    default_currency: str,
) -> InlineKeyboardMarkup:
    normalized_current = current_currency.upper()
    default_active = normalized_current == default_currency.upper()
    return _preset_picker(
        [
            choice_button(
                code,
                f"public_sub_currency:{subscription_id}:{code}",
                selected=code == normalized_current and not default_active,
            )
            for code in CURRENCY_PRESETS
        ],
        columns=3,
        other_callback=f"public_sub_currency_other:{subscription_id}",
        default_button=choice_button(
            DEFAULT_TEXT,
            _subscription_callback(subscription_id, "public_currency_default"),
            selected=default_active,
        ),
        back_callback=_subscription_callback(subscription_id, "open_public"),
    )


def subscription_currency_keyboard(
    subscription_id: int,
    current_currency: str,
) -> InlineKeyboardMarkup:
    normalized_current = current_currency.upper()
    return _preset_picker(
        [
            choice_button(code, f"sub_currency:{subscription_id}:{code}", selected=code == normalized_current)
            for code in CURRENCY_PRESETS
        ],
        columns=3,
        other_callback=f"sub_currency_other:{subscription_id}",
        default_button=None,
        back_callback=_subscription_callback(subscription_id, "pricing"),
    )


def public_settings_time_keyboard(current_time: str, default_time: str) -> InlineKeyboardMarkup:
    normalized_current = current_time.strip()
    default_active = normalized_current == default_time.strip()
    return _preset_picker(
        _time_preset_buttons("public_settings_time", normalized_current, default_active=default_active),
        columns=2,
        other_callback="public_settings:time_other",
        default_button=choice_button(DEFAULT_TEXT, "public_settings:time_reset", selected=default_active),
        back_callback="public_settings:menu",
    )


def public_settings_timezone_keyboard(current_timezone: str, default_timezone: str) -> InlineKeyboardMarkup:
    normalized_current = current_timezone.strip()
    default_active = normalized_current == default_timezone.strip()
    return _preset_picker(
        [
            choice_button(
                zone,
                f"public_settings_timezone:{zone}",
                selected=zone == normalized_current and not default_active,
            )
            for zone in COMMON_TIMEZONES
        ],
        columns=2,
        other_callback="public_settings:timezone_other",
        default_button=choice_button(DEFAULT_TEXT, "public_settings:timezone_reset", selected=default_active),
        back_callback="public_settings:menu",
    )


def _checklist_keyboard(options: Sequence[tuple[bool, str, str]], back_callback: str) -> InlineKeyboardMarkup:
    """One option per row, ✅/☐ in front; checked options are green."""
    rows = []
    for is_checked, label, callback_data in options:
        if is_checked:
            button = InlineKeyboardButton(text=f"✅ {label}", callback_data=callback_data, style=STYLE_SUCCESS)
        else:
            button = InlineKeyboardButton(text=f"☐ {label}", callback_data=callback_data)
        rows.append([button])
    rows.append(nav_row(back_callback))
    return _markup(rows)


def settings_rounding_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    options = (
        ("precise", "With cents"),
        ("floor", "Round down"),
        ("round", "Round correctly"),
        ("ceil", "Round up"),
    )
    return _checklist_keyboard(
        [(current_mode == mode, label, f"settings_rounding:{mode}") for mode, label in options],
        "settings:menu",
    )


def settings_notifications_keyboard(
    reminders_enabled: bool,
    paid_enabled: bool,
    closed_enabled: bool,
) -> InlineKeyboardMarkup:
    return _checklist_keyboard(
        (
            (reminders_enabled, "Payment reminders", "settings_notify:reminders"),
            (paid_enabled, "Payment recorded", "settings_notify:paid"),
            (closed_enabled, "All paid (cycle closed)", "settings_notify:closed"),
        ),
        "settings:menu",
    )


def build_period_keyboard(*, force_reply: bool = True) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=f"{days} d", callback_data=f"period:{days}") for days in (7, 14, 30, 90)]
    buttons.append(InlineKeyboardButton(text="Monthly", callback_data="period:month"))
    rows = grid(buttons, 2)
    rows.append([dialog_cancel_inline_button()])
    return _prompt_markup(rows, force_reply)


def build_share_limit_keyboard(*, force_reply: bool = True) -> InlineKeyboardMarkup:
    return _prompt_markup(
        [
            [InlineKeyboardButton(text="Split across all", callback_data="sharelimit:all")],
            [dialog_cancel_inline_button()],
        ],
        force_reply,
    )


def build_creation_payment_mode_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            [
                InlineKeyboardButton(text="Split by shares", callback_data=f"create_payment_mode:{PAYMENT_MODE_SPLIT}"),
                InlineKeyboardButton(text="Fixed per user", callback_data=f"create_payment_mode:{PAYMENT_MODE_FIXED}"),
            ],
            [dialog_cancel_inline_button()],
        ]
    )


def build_due_date_change_keyboard(
    subscription_id: int,
    old_due: str,
    new_due: str,
) -> InlineKeyboardMarkup:
    def action(name: str) -> str:
        return DueDateChangeAction(
            action=name,
            subscription_id=subscription_id,
            old_due=old_due,
            new_due=new_due,
        ).pack()

    return _markup(
        [
            [InlineKeyboardButton(text="🔀 Move cycle (keep payments)", callback_data=action("move"))],
            [InlineKeyboardButton(text="🆕 New cycle (request payments)", callback_data=action("new"))],
            [dialog_cancel_inline_button()],
        ]
    )


def _due_value(due_date: date | str) -> str:
    return due_date if isinstance(due_date, str) else due_date.isoformat()


def build_payment_confirmation_keyboard(
    subscription_id: int,
    due_date: date | str,
    payment_details: str = "",
    payment_link: str = "",
) -> InlineKeyboardMarkup:
    rows = payment_requisite_rows(payment_details, payment_link)
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Paid",
                callback_data=ReminderAction(subscription_id=subscription_id, due_date=_due_value(due_date)).pack(),
                style=STYLE_SUCCESS,
            )
        ]
    )
    return _markup(rows)


def build_batch_payment_confirmation_keyboard(
    items: Sequence[Dict[str, object]],
    payment_details: str = "",
    payment_link: str = "",
) -> InlineKeyboardMarkup:
    rows = payment_requisite_rows(payment_details, payment_link)
    for item in items:
        due_str = _due_value(item.get("due_date"))
        label = str(item.get("subscription_label") or item.get("subscription_name") or "Subscription")
        due_hint = str(item.get("due_date_text") or due_str)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ {label} · {due_hint}",
                    callback_data=ReminderAction(subscription_id=int(item["subscription_id"]), due_date=due_str).pack(),
                    style=STYLE_SUCCESS,
                )
            ]
        )
    return _markup(rows)


def build_test_payment_confirmation_keyboard(
    subscription_id: int,
    due_date: date | str,
    payment_details: str = "",
    payment_link: str = "",
) -> InlineKeyboardMarkup:
    rows = payment_requisite_rows(payment_details, payment_link)
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Paid",
                callback_data=TestPaidAction(subscription_id=subscription_id, due_date=_due_value(due_date)).pack(),
                style=STYLE_SUCCESS,
            )
        ]
    )
    return _markup(rows)


def comment_edit_keyboard(
    subscription_id: int,
    has_comment: bool,
    *,
    force_reply: bool = False,
) -> InlineKeyboardMarkup:
    """Comment prompt keyboard; ``force_reply`` only when sent as a fresh message (never on edit paths)."""
    rows: list[list[InlineKeyboardButton]] = []
    if has_comment:
        rows.append([danger_button("Clear", _subscription_callback(subscription_id, "comment_clear"))])
    rows.append([dialog_cancel_inline_button()])
    rows.append(nav_row())
    return _prompt_markup(rows, force_reply)
