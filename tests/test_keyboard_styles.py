"""Semantic button colours, force_reply prompts, stable pagination rows, the main menu and the invite copy button."""

import unittest

from app.handlers.members import invite_link_keyboard
from app.ui.keyboards import (
    COPY_TEXT_MAX_LEN,
    admin_reply_keyboard,
    build_currency_keyboard,
    build_members_list_keyboard,
    build_period_keyboard,
    build_share_limit_keyboard,
    build_subscription_list_keyboard,
    comment_edit_keyboard,
    dialog_cancel_inline_keyboard,
    member_balance_currency_keyboard,
    member_balance_keyboard,
    member_delete_confirm_keyboard,
    member_detail_keyboard,
    member_payment_destination_keyboard,
    pagination_row,
    participants_settings_keyboard,
    payment_destination_delete_keyboard,
    payment_destination_detail_keyboard,
    payment_destinations_keyboard,
    public_account_keyboard,
    public_reply_keyboard,
    public_settings_time_keyboard,
    public_settings_timezone_keyboard,
    public_subscription_currency_keyboard,
    public_subscription_reminder_time_keyboard,
    reminder_send_targets_keyboard,
    reminder_settings_keyboard,
    settings_time_keyboard,
    settings_tests_keyboard,
    subscription_base_currency_keyboard,
    subscription_currency_keyboard,
    subscription_delete_confirm_keyboard,
    subscription_detail_keyboard,
    subscription_more_keyboard,
    subscription_payment_destination_keyboard,
    subscription_reminder_time_keyboard,
    subscription_user_amounts_keyboard,
    tests_menu_keyboard,
    topup_request_review_keyboard,
    user_amount_clear_keyboard,
)

NAV_TEXTS = {"⬅️ Back", "✖️ Close", "Next ▶️", "◀️", "▶️"}


def _dump(markup) -> dict:
    return markup.model_dump(exclude_none=True)


def _buttons(markup) -> list[dict]:
    return [button for row in _dump(markup)["inline_keyboard"] for button in row]


def _button(markup, text: str) -> dict:
    for button in _buttons(markup):
        if button["text"] == text:
            return button
    raise AssertionError(f"button {text!r} not found in {_buttons(markup)!r}")


class PrimaryActionTests(unittest.TestCase):
    def _assert_single_primary(self, markup, text: str) -> None:
        primary = [button["text"] for button in _buttons(markup) if button.get("style") == "primary"]
        self.assertEqual(primary, [text])
        for button in _buttons(markup):
            if button["text"] in NAV_TEXTS:
                self.assertNotIn("style", button, button)

    def test_new_subscription_is_the_primary_action(self):
        markup = build_subscription_list_keyboard([{"id": 1, "name": "Netflix", "amount": 9.5, "currency": "USD"}])
        self._assert_single_primary(markup, "➕ New subscription")

    def test_add_user_is_the_primary_action(self):
        markup = build_members_list_keyboard([{"id": 1, "full_name": "Anna"}], total_users=1)
        self._assert_single_primary(markup, "➕ Add user")

    def test_add_payment_method_is_the_primary_action(self):
        markup = payment_destinations_keyboard([{"id": 1, "title": "Card", "currency": "RUB"}], 1, 0)
        self._assert_single_primary(markup, "➕ Add payment method")

    def test_top_up_is_the_primary_action(self):
        self._assert_single_primary(public_account_keyboard(), "➕ Top up")

    def test_balance_set_is_the_primary_action(self):
        self._assert_single_primary(member_balance_keyboard(7), "✏️ Set")

    def test_set_all_is_the_primary_action(self):
        participants = [{"id": 1, "full_name": "Anna", "share_weight": 1, "fixed_amount": None}]
        self._assert_single_primary(subscription_user_amounts_keyboard(3, participants, "usd", 10.0), "✏️ Set all")

    def test_send_reminders_now_is_the_primary_action(self):
        self._assert_single_primary(reminder_settings_keyboard(3), "📬 Send reminders now")

    def test_send_to_all_is_the_primary_action(self):
        markup = reminder_send_targets_keyboard(3, [{"full_name": "Anna", "telegram_id": 42}])
        self._assert_single_primary(markup, "📬 All")

    def test_send_test_reminders_is_the_primary_action(self):
        self._assert_single_primary(tests_menu_keyboard(), "📬 Send test reminders")


class DeleteConfirmationTests(unittest.TestCase):
    def test_member_delete_confirm_is_red_with_bin_label(self):
        button = _button(member_delete_confirm_keyboard(5), "🗑 Yes, delete")
        self.assertEqual(button["style"], "danger")
        self.assertEqual(button["callback_data"], "member:confirm_delete:5")
        self.assertNotIn("style", _button(member_delete_confirm_keyboard(5), "⬅️ Back"))

    def test_payment_destination_delete_confirm_is_red_with_bin_label(self):
        button = _button(payment_destination_delete_keyboard(9), "🗑 Yes, delete")
        self.assertEqual(button["style"], "danger")
        self.assertEqual(button["callback_data"], "paydest:confirm_delete:9")

    def test_subscription_delete_confirm_is_red_with_full_navigation(self):
        dumped = _dump(subscription_delete_confirm_keyboard(3))
        self.assertEqual(
            dumped["inline_keyboard"],
            [
                [{"text": "🗑 Yes, delete", "callback_data": "sub:confirm_delete:3", "style": "danger"}],
                [
                    {"text": "⬅️ Back", "callback_data": "sub:more:3"},
                    {"text": "✖️ Close", "callback_data": "menu:close"},
                ],
            ],
        )

    def test_delete_entry_buttons_are_red_and_alone_on_their_row(self):
        for markup in (
            member_detail_keyboard(5),
            payment_destination_detail_keyboard(9, is_default=False),
            subscription_more_keyboard(3),
        ):
            with self.subTest(markup=markup):
                rows = _dump(markup)["inline_keyboard"]
                delete_rows = [row for row in rows if any(button["text"] == "🗑 Delete" for button in row)]
                self.assertEqual(len(delete_rows), 1)
                self.assertEqual(len(delete_rows[0]), 1)
                self.assertEqual(delete_rows[0][0]["style"], "danger")
                # The destructive action sits right above the navigation row.
                self.assertIs(rows[-2], delete_rows[0])

    def test_clear_buttons_are_red(self):
        self.assertEqual(_button(comment_edit_keyboard(3, True), "Clear")["style"], "danger")
        self.assertEqual(_button(user_amount_clear_keyboard(3, 4), "Clear")["style"], "danger")

    def test_dialog_cancel_stays_red(self):
        self.assertEqual(_button(dialog_cancel_inline_keyboard(), "Cancel")["style"], "danger")

    def test_approve_and_reject_share_a_row(self):
        first_row = _dump(topup_request_review_keyboard(4))["inline_keyboard"][0]
        self.assertEqual([button["text"] for button in first_row], ["✅ Approve", "✖️ Reject"])
        self.assertEqual([button["style"] for button in first_row], ["success", "danger"])


class ForceReplyTests(unittest.TestCase):
    def test_sent_prompt_keyboard_carries_force_reply(self):
        dumped = _dump(dialog_cancel_inline_keyboard())
        self.assertIs(dumped["force_reply"], True)
        self.assertEqual(dumped["inline_keyboard"], [[{"text": "Cancel", "callback_data": "dialog:cancel", "style": "danger"}]])

    def test_edit_variant_has_no_force_reply(self):
        dumped = _dump(dialog_cancel_inline_keyboard(force_reply=False))
        self.assertNotIn("force_reply", dumped)
        self.assertEqual(dumped["inline_keyboard"][0][0]["callback_data"], "dialog:cancel")

    def test_builder_based_prompts_keep_force_reply(self):
        comment_markup = comment_edit_keyboard(3, True, force_reply=True)
        for markup in (
            build_currency_keyboard(("usd", "eur")),
            build_period_keyboard(),
            build_share_limit_keyboard(),
            user_amount_clear_keyboard(3, 4),
            comment_markup,
        ):
            with self.subTest(markup=markup):
                dumped = _dump(markup)
                self.assertIs(dumped["force_reply"], True)
                cancel_row = -2 if markup is comment_markup else -1
                self.assertEqual(dumped["inline_keyboard"][cancel_row][0]["callback_data"], "dialog:cancel")

    def test_builder_based_prompts_drop_force_reply_on_edit_paths(self):
        for markup in (
            build_currency_keyboard(("usd",), force_reply=False),
            build_period_keyboard(force_reply=False),
            build_share_limit_keyboard(force_reply=False),
            user_amount_clear_keyboard(3, 4, force_reply=False),
            comment_edit_keyboard(3, False),
        ):
            with self.subTest(markup=markup):
                self.assertNotIn("force_reply", _dump(markup))

    def test_currency_keyboard_callbacks_are_unchanged(self):
        dumped = _dump(build_currency_keyboard(("usd", "eur", "rub")))
        self.assertEqual(
            [button["callback_data"] for button in dumped["inline_keyboard"][0]],
            ["currency:USD", "currency:EUR", "currency:RUB"],
        )


class PaginationRowTests(unittest.TestCase):
    def _nav_row(self, markup) -> list[dict]:
        rows = _dump(markup)["inline_keyboard"]
        nav_rows = [row for row in rows if any(button["text"] in {"◀️", "▶️"} for button in row)]
        self.assertLessEqual(len(nav_rows), 1)
        return nav_rows[0] if nav_rows else []

    def test_first_page_disables_previous_arrow(self):
        row = self._nav_row(build_members_list_keyboard([], page=1, total_pages=3))
        self.assertEqual(
            row,
            [
                {"text": "◀️", "disabled": {}},
                {"text": "1 / 3", "disabled": {}},
                {"text": "▶️", "callback_data": "member:page:2"},
            ],
        )

    def test_middle_page_enables_both_arrows(self):
        row = self._nav_row(build_members_list_keyboard([], page=2, total_pages=3))
        self.assertEqual(
            row,
            [
                {"text": "◀️", "callback_data": "member:page:1"},
                {"text": "2 / 3", "disabled": {}},
                {"text": "▶️", "callback_data": "member:page:3"},
            ],
        )

    def test_last_page_disables_next_arrow(self):
        row = self._nav_row(settings_tests_keyboard([], page=3, total_pages=3))
        self.assertEqual(
            row,
            [
                {"text": "◀️", "callback_data": "testlist:page:2"},
                {"text": "3 / 3", "disabled": {}},
                {"text": "▶️", "disabled": {}},
            ],
        )

    def test_single_page_renders_no_pagination_row(self):
        self.assertEqual(self._nav_row(build_members_list_keyboard([], page=1, total_pages=1)), [])
        self.assertEqual(self._nav_row(settings_tests_keyboard([], page=1, total_pages=1)), [])

    def test_pagination_row_helper_shape(self):
        row = pagination_row(1, 1, previous_callback="x:0", next_callback="x:2")
        self.assertEqual(len(row), 3)
        self.assertTrue(all(button.model_dump(exclude_none=True).get("disabled") == {} for button in row))

    def test_other_buttons_are_unchanged(self):
        markup = settings_tests_keyboard([{"full_name": "Anna", "telegram_id": 42}], page=1, total_pages=2, total_users=1)
        rows = _dump(markup)["inline_keyboard"]
        self.assertEqual(rows[0], [{"text": "Anna", "callback_data": "testsend:42"}])
        self.assertEqual(
            rows[-1],
            [
                {"text": "⬅️ Back", "callback_data": "settings:tests"},
                {"text": "✖️ Close", "callback_data": "menu:close"},
            ],
        )


class MainMenuTests(unittest.TestCase):
    def test_menus_are_persistent_with_a_placeholder(self):
        for markup in (admin_reply_keyboard(), public_reply_keyboard()):
            with self.subTest(markup=markup):
                dumped = _dump(markup)
                self.assertIs(dumped["is_persistent"], True)
                self.assertIs(dumped["resize_keyboard"], True)
                self.assertEqual(dumped["input_field_placeholder"], "Choose a section")

    def test_labels_still_match_the_text_handlers(self):
        # The handlers match these exact strings (F.text == ...), so a label
        # change here must come with a handler change.
        admin_texts = [button["text"] for row in _dump(admin_reply_keyboard())["keyboard"] for button in row]
        public_texts = [button["text"] for row in _dump(public_reply_keyboard())["keyboard"] for button in row]
        self.assertEqual(admin_texts, ["👥 Users", "📋 Subscriptions", "💳 Payment", "📊 Reports", "⚙️ Settings"])
        self.assertEqual(public_texts, ["👤 Account", "📋 Subscriptions", "📊 Reports", "⚙️ Settings"])

    def test_one_highlighted_section_per_menu(self):
        for markup, highlighted in ((admin_reply_keyboard(), "📋 Subscriptions"), (public_reply_keyboard(), "👤 Account")):
            with self.subTest(highlighted=highlighted):
                styled = [
                    (button["text"], button["style"])
                    for row in _dump(markup)["keyboard"]
                    for button in row
                    if "style" in button
                ]
                self.assertEqual(styled, [(highlighted, "primary")])


class SelectedOptionTests(unittest.TestCase):
    """Every picker marks its current option the same way: a ✅ prefix and green."""

    PICKERS = {
        "member balance currency": (lambda: member_balance_currency_keyboard(7, "eur"), "✅ EUR"),
        "subscription currency": (lambda: subscription_currency_keyboard(3, "usd"), "✅ USD"),
        "convert currency": (lambda: subscription_base_currency_keyboard(3, "rub"), "✅ RUB"),
        "member currency override": (lambda: public_subscription_currency_keyboard(3, "usd", "rub"), "✅ USD"),
        "member currency default": (lambda: public_subscription_currency_keyboard(3, "rub", "rub"), "✅ Default"),
        "admin base time": (lambda: settings_time_keyboard("12:00"), "✅ 12:00"),
        "subscription time": (lambda: subscription_reminder_time_keyboard(3, "20:00", "16:00"), "✅ 20:00"),
        "subscription time default": (lambda: subscription_reminder_time_keyboard(3, "16:00", "16:00"), "✅ Default"),
        "member time": (lambda: public_subscription_reminder_time_keyboard(3, "09:00", "16:00"), "✅ 09:00"),
        "member base time default": (lambda: public_settings_time_keyboard("16:00", "16:00"), "✅ Default"),
        "member timezone": (lambda: public_settings_timezone_keyboard("UTC", "Europe/Moscow"), "✅ UTC"),
        "member timezone default": (
            lambda: public_settings_timezone_keyboard("Europe/Moscow", "Europe/Moscow"),
            "✅ Default",
        ),
        "payment mode": (lambda: participants_settings_keyboard(3, "fixed"), "✅ Fixed per user"),
        "member payment method": (
            lambda: member_payment_destination_keyboard(7, [{"id": 2, "title": "Wise", "currency": "EUR"}], 2, None),
            "✅ Wise (EUR)",
        ),
        "subscription payment method default": (
            lambda: subscription_payment_destination_keyboard(3, [{"id": 2, "title": "Wise", "currency": "EUR"}], None, 2),
            "✅ Default (Wise · EUR)",
        ),
    }

    def test_exactly_one_option_is_ticked_and_green(self):
        for name, (factory, expected) in self.PICKERS.items():
            with self.subTest(picker=name):
                buttons = _buttons(factory())
                green = [button["text"] for button in buttons if button.get("style") == "success"]
                ticked = [button["text"] for button in buttons if button["text"].startswith("✅ ")]
                self.assertEqual(green, [expected])
                self.assertEqual(ticked, [expected])

    def test_other_and_default_share_a_row(self):
        rows = _dump(public_settings_time_keyboard("12:00", "16:00"))["inline_keyboard"]
        self.assertEqual(
            rows[-2],
            [
                {"text": "✏️ Other", "callback_data": "public_settings:time_other"},
                {"text": "Default", "callback_data": "public_settings:time_reset"},
            ],
        )


class LayoutTests(unittest.TestCase):
    def _texts(self, markup) -> list[list[str]]:
        return [[button["text"] for button in row] for row in _dump(markup)["inline_keyboard"]]

    def test_subscription_card_uses_a_two_column_grid(self):
        self.assertEqual(
            self._texts(subscription_detail_keyboard(3)),
            [
                ["💰 Pricing & schedule"],
                ["👥 Participants", "🔔 Reminders"],
                ["💳 Payment", "📊 Reports"],
                ["✏️ Rename"],
                ["⬅️ Back", "✖️ Close"],
            ],
        )

    def test_pending_user_card_leads_with_the_auth_link(self):
        rows = _dump(member_detail_keyboard(5, is_pending=True))["inline_keyboard"]
        self.assertEqual(rows[0], [{"text": "🔗 Auth link", "callback_data": "member:invite:5", "style": "primary"}])
        self.assertEqual([button["text"] for button in rows[1]], ["✏️ Rename", "📊 Reports"])

    def test_default_payment_method_is_starred_in_the_list(self):
        markup = payment_destinations_keyboard(
            [{"id": 1, "title": "Card", "currency": "RUB"}, {"id": 2, "title": "Wise", "currency": "EUR"}],
            1,
            0,
        )
        texts = [button["text"] for button in _buttons(markup)]
        self.assertIn("⭐ Card (RUB)", texts)
        self.assertIn("Wise (EUR)", texts)


class InviteCopyLinkTests(unittest.TestCase):
    def test_copy_link_button(self):
        link = "https://t.me/pingsubs_bot?start=join_abc"
        dumped = _dump(invite_link_keyboard(link))
        self.assertEqual(
            dumped,
            {"inline_keyboard": [[{"text": "📋 Copy link", "style": "primary", "copy_text": {"text": link}}]]},
        )

    def test_copy_text_is_trimmed_to_telegram_limit(self):
        link = "https://t.me/pingsubs_bot?start=" + "x" * 300
        dumped = _dump(invite_link_keyboard(link))
        self.assertEqual(len(dumped["inline_keyboard"][0][0]["copy_text"]["text"]), COPY_TEXT_MAX_LEN)


if __name__ == "__main__":
    unittest.main()
