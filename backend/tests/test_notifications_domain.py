"""MOD-013 ENG-02 decisions, tested without a database.

The template contract, the preference rules and the delivery state machine: what each refuses,
and why the refusal is the control rather than a formality.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, time

from app.notifications import delivery, preferences, templates

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def template(**kwargs: object) -> templates.TemplateVersion:
    body: dict = {
        "template_key": "invoice.issued", "version": 1, "category": "transactional",
        "channel": "email", "locale": "en", "subject": "Invoice {{ number }}",
        "body": "Your invoice {{ number }} is ready.", "variables": ("number",),
    }
    body.update(kwargs)
    return templates.TemplateVersion(**body)  # type: ignore[arg-type]


class TemplateTests(unittest.TestCase):
    def test_a_placeholder_nobody_declared_is_refused(self) -> None:
        """An undeclared placeholder renders as the literal `{{ amount }}` in a member's
        inbox, which is the failure everybody has seen in a real product."""
        with self.assertRaises(templates.TemplateError) as caught:
            templates.check_version(template(body="You owe {{ amount }}.",
                                             variables=("number",)))
        self.assertIn("renders literally", str(caught.exception))

    def test_a_declared_variable_nothing_uses_is_refused(self) -> None:
        """A caller supplying it would believe the value reached the message."""
        with self.assertRaises(templates.TemplateError):
            templates.check_version(template(variables=("number", "amount")))

    def test_only_email_carries_a_subject(self) -> None:
        with self.assertRaises(templates.TemplateError):
            templates.check_version(template(channel="sms", subject="Hello",
                                             body="Hi {{ number }}."))
        with self.assertRaises(templates.TemplateError):
            templates.check_version(template(subject=""))
        templates.check_version(template(channel="sms", subject="",
                                         body="Invoice {{ number }} ready."))

    def test_the_category_cannot_change_between_versions(self) -> None:
        """A template that moved from transactional to marketing would have notifications
        already sent under the old consent rules, and the other way would let a campaign ride
        on a receipt's exemption from opt-out."""
        with self.assertRaises(templates.TemplateError) as caught:
            templates.check_succession(template(), template(version=2, category="marketing"))
        self.assertIn("category", str(caught.exception))

    def test_the_channel_and_locale_cannot_change_either(self) -> None:
        for change in ({"channel": "sms", "subject": ""}, {"locale": "is"}):
            with self.assertRaises(templates.TemplateError):
                templates.check_succession(template(), template(version=2, **change))

    def test_a_later_version_may_not_drop_a_variable(self) -> None:
        with self.assertRaises(templates.TemplateError):
            templates.check_succession(
                template(subject="Invoice {{ number }} {{ amount }}",
                         variables=("number", "amount")),
                template(version=2))

    def test_a_value_is_never_itself_expanded(self) -> None:
        """A second substitution pass would be a template-injection primitive: the values come
        from a caller and the text comes from a tenant author."""
        subject, body = templates.render(template(), {"number": "{{ amount }}"})
        self.assertEqual(subject, "Invoice {{ amount }}")
        self.assertIn("{{ amount }}", body)

    def test_rendering_is_checked_in_both_directions(self) -> None:
        with self.assertRaises(templates.TemplateError):
            templates.render(template(), {})
        with self.assertRaises(templates.TemplateError):
            templates.render(template(), {"number": "1", "extra": "x"})

    def test_only_marketing_needs_consent(self) -> None:
        self.assertTrue(template(category="marketing").needs_consent)
        for category in ("transactional", "operational", "coaching"):
            self.assertFalse(template(category=category).needs_consent)

    def test_only_coaching_and_marketing_may_be_muted(self) -> None:
        self.assertEqual(set(templates.OPTIONAL_CATEGORIES), {"coaching", "marketing"})
        self.assertFalse(template(category="transactional").is_suppressible_by_preference)


class PreferenceTests(unittest.TestCase):
    def preference(self, **kwargs: object) -> preferences.Preference:
        body: dict = {"category": "marketing", "channel": "email"}
        body.update(kwargs)
        return preferences.Preference(**body)  # type: ignore[arg-type]

    def test_a_transactional_message_cannot_be_switched_off(self) -> None:
        """A tenant unable to tell somebody their payment failed because they muted marketing
        has confused courtesy with correctness."""
        with self.assertRaises(preferences.PreferenceError):
            preferences.check_preference(
                self.preference(category="transactional", allowed=False))
        preferences.check_preference(self.preference(allowed=False))

    def test_quiet_hours_need_both_ends_and_a_timezone(self) -> None:
        with self.assertRaises(preferences.PreferenceError):
            preferences.check_preference(self.preference(quiet_from=time(22)))
        with self.assertRaises(preferences.PreferenceError):
            preferences.check_preference(
                self.preference(quiet_from=time(22), quiet_until=time(7)))
        preferences.check_preference(
            self.preference(quiet_from=time(22), quiet_until=time(7),
                            timezone="Atlantic/Reykjavik"))

    def test_a_quiet_window_wraps_midnight(self) -> None:
        """22:00 to 07:00 is the ordinary case and the one a naive `start <= t <= end` gets
        wrong, by treating the quietest hours of the night as the only ones that are loud."""
        pref = self.preference(quiet_from=time(22), quiet_until=time(7), timezone="UTC")
        self.assertTrue(preferences.in_quiet_hours(pref, NOW.replace(hour=23)))
        self.assertTrue(preferences.in_quiet_hours(pref, NOW.replace(hour=3)))
        self.assertFalse(preferences.in_quiet_hours(pref, NOW.replace(hour=12)))

    def test_a_quiet_window_is_the_recipients_own_zone(self) -> None:
        pref = self.preference(quiet_from=time(22), quiet_until=time(7),
                               timezone="Asia/Tokyo")
        # 14:00 UTC is 23:00 in Tokyo.
        self.assertTrue(preferences.in_quiet_hours(pref, NOW.replace(hour=14)))
        self.assertFalse(preferences.in_quiet_hours(pref, NOW.replace(hour=2)))

    def test_suppression_beats_a_critical_alert(self) -> None:
        """A bounce is the channel saying the address is wrong; a critical alert that cannot
        reach somebody is a routing problem, not a licence to keep sending."""
        decision = preferences.decide(
            preferences.Request(category="transactional", channel="email", priority="critical",
                                bypass_policy_ref="RB-ENG-02#alerts", suppressed=True),
            None, at=NOW)
        self.assertEqual(decision.outcome, "suppress")

    def test_a_critical_alert_must_name_its_policy(self) -> None:
        with self.assertRaises(preferences.PreferenceError) as caught:
            preferences.decide(
                preferences.Request(category="coaching", channel="email", priority="critical"),
                self.preference(category="coaching", allowed=False), at=NOW)
        self.assertIn("documented policy", str(caught.exception))

    def test_a_critical_alert_with_a_policy_bypasses_an_opt_out(self) -> None:
        decision = preferences.decide(
            preferences.Request(category="coaching", channel="email", priority="critical",
                                bypass_policy_ref="RB-ENG-02#alerts"),
            self.preference(category="coaching", allowed=False), at=NOW)
        self.assertEqual((decision.outcome, decision.reason), ("send", "critical_bypass"))

    def test_a_disabled_channel_falls_back_once(self) -> None:
        channel, refusal = preferences.resolve_channel(
            "email", channel_enabled=False, fallback_channel="sms")
        self.assertEqual((channel, refusal), ("sms", None))
        nowhere, why = preferences.resolve_channel(
            "email", channel_enabled=False, fallback_channel=None)
        self.assertEqual((nowhere, why), (None, "channel_disabled_and_no_fallback"))

    def test_an_enabled_channel_is_the_one_asked_for(self) -> None:
        self.assertEqual(
            preferences.resolve_channel("email", channel_enabled=True, fallback_channel="sms"),
            ("email", None))

    def test_the_decision_evaluates_only_the_channel_it_was_given(self) -> None:
        """**The review finding, as a test.**

        `decide` no longer resolves a fallback, so it cannot apply one channel's preference to
        another channel's message. The caller resolves first and reads every per-channel fact
        for the resolved channel; what is left here is that `decide` refuses to look anywhere
        else.
        """
        opted_out_of_sms = self.preference(category="coaching", channel="sms", allowed=False)
        with self.assertRaises(preferences.PreferenceError):
            preferences.decide(
                preferences.Request(category="coaching", channel="sms"),
                self.preference(category="marketing", channel="sms", allowed=True), at=NOW)
        decision = preferences.decide(
            preferences.Request(category="coaching", channel="sms"), opted_out_of_sms, at=NOW)
        self.assertEqual(
            (decision.outcome, decision.reason, decision.channel),
            ("suppress", "recipient_opted_out", "sms"))

    def test_quiet_hours_defer_rather_than_suppress(self) -> None:
        """The member still wants the message, later."""
        pref = self.preference(quiet_from=time(22), quiet_until=time(7), timezone="UTC")
        decision = preferences.decide(
            preferences.Request(category="marketing", channel="email"), pref,
            at=NOW.replace(hour=23))
        self.assertEqual(decision.outcome, "defer")
        assert decision.send_after is not None
        self.assertEqual(decision.send_after.astimezone(UTC).hour, 7)

    def test_a_frequency_cap_digests_rather_than_dropping(self) -> None:
        """Nothing is lost, which is what makes a cap safe to set low."""
        decision = preferences.decide(
            preferences.Request(category="marketing", channel="email", sent_today=5),
            self.preference(daily_cap=5), at=NOW)
        self.assertEqual((decision.outcome, decision.reason),
                         ("digest", "daily_cap_reached"))

    def test_no_preference_at_all_sends(self) -> None:
        decision = preferences.decide(
            preferences.Request(category="operational", channel="email"), None, at=NOW)
        self.assertEqual(decision.outcome, "send")

    def test_a_preference_applies_to_its_own_category(self) -> None:
        with self.assertRaises(preferences.PreferenceError):
            preferences.decide(
                preferences.Request(category="coaching", channel="email"),
                self.preference(category="marketing"), at=NOW)


class DeliveryTests(unittest.TestCase):
    def test_a_digest_is_normalized_and_channel_scoped(self) -> None:
        """`A@B.com` and `a@b.com` are one mailbox, and a bounce on email must not suppress
        an SMS."""
        self.assertEqual(delivery.address_digest("email", " A@B.com "),
                         delivery.address_digest("email", "a@b.com"))
        self.assertNotEqual(delivery.address_digest("email", "a@b.com"),
                            delivery.address_digest("sms", "a@b.com"))

    def test_a_blank_address_has_no_digest(self) -> None:
        with self.assertRaises(delivery.DeliveryError):
            delivery.address_digest("email", "   ")

    def test_a_bounce_is_terminal_on_the_first_report(self) -> None:
        """A retry after a bounce is the thing that gets a sending domain blocked."""
        verdict = delivery.outcome_verdict(outcome="bounced", attempts=1, max_attempts=5,
                                           now=NOW)
        self.assertEqual((verdict.state, verdict.suppress_reason), ("dead", "bounced"))
        self.assertIsNone(verdict.next_attempt_at)

    def test_a_complaint_suppresses_too(self) -> None:
        verdict = delivery.outcome_verdict(outcome="complained", attempts=1, max_attempts=5,
                                           now=NOW)
        self.assertEqual((verdict.state, verdict.suppress_reason), ("dead", "complained"))

    def test_an_ordinary_failure_gets_the_budget(self) -> None:
        early = delivery.outcome_verdict(outcome="failed", attempts=1, max_attempts=3,
                                         now=NOW)
        self.assertEqual(early.state, "failed")
        assert early.next_attempt_at is not None
        self.assertGreater(early.next_attempt_at, NOW)
        last = delivery.outcome_verdict(outcome="failed", attempts=3, max_attempts=3, now=NOW)
        self.assertEqual(last.state, "dead")
        self.assertIsNone(last.suppress_reason)

    def test_a_delivered_message_is_terminal(self) -> None:
        for target in delivery.DELIVERY_STATES:
            with self.assertRaises(delivery.DeliveryError):
                delivery.check_transition("delivered", target)

    def test_a_failed_delivery_may_be_sent_again(self) -> None:
        delivery.check_transition("failed", "sent")
        delivery.check_transition("pending", "suppressed")
        with self.assertRaises(delivery.DeliveryError):
            delivery.check_transition("suppressed", "sent")

    def test_only_an_unsubscribe_may_be_released(self) -> None:
        """A bounce or a complaint is the channel's judgement about deliverability, and
        overriding it damages every other notification's chance of arriving -- including the
        transactional ones nobody opted out of."""
        delivery.check_release("unsubscribed")
        for reason in ("bounced", "complained"):
            with self.assertRaises(delivery.DeliveryError) as caught:
                delivery.check_release(reason)
            self.assertIn("channel's judgement", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
