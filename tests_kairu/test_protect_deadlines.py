"""Protection (Phase J): deadlines you add, deadlines found in emails, and the reminders before each."""

from datetime import datetime, timedelta, timezone

import pytest

from kairu.protect import deadlines
from kairu.protect.mailrules import Mail
from kairu.protect.store import ProtectStore

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 27, 23, 0, tzinfo=IST)  # a Tuesday evening


@pytest.mark.parametrize("text,due,ambiguous", [
    ("Submissions close on 30/10/2026 at 6 pm", datetime(2026, 10, 30, 18, 0, tzinfo=IST), False),
    ("The deadline is 2026-11-05 18:00", datetime(2026, 11, 5, 18, 0, tzinfo=IST), False),
    ("Deadline: Nov 5, 2026, 11:59 PM", datetime(2026, 11, 5, 23, 59, tzinfo=IST), False),
    ("Last date to apply is 5th November", datetime(2026, 11, 5, 23, 59, tzinfo=IST), False),
    ("Registrations close tomorrow at 11:59 PM IST", datetime(2026, 10, 28, 23, 59, tzinfo=IST), False),
    ("Please submit by 05/11/2026", datetime(2026, 11, 5, 23, 59, tzinfo=IST), True),
    ("Due on 11/30/2026 noon", datetime(2026, 11, 30, 12, 0, tzinfo=IST), False),
    ("Apply by Jan 10", datetime(2027, 1, 10, 23, 59, tzinfo=IST), False),
])
def test_dates_are_read_day_first_and_say_when_they_could_be_read_two_ways(text, due, ambiguous):
    found = deadlines.find_date(text, NOW, IST)
    assert found == (due, ambiguous)


def test_a_utc_time_is_converted_to_your_time():
    due, _ = deadlines.find_date("Submissions close 2026-11-01 at 12:00 UTC", NOW, IST)
    assert due == datetime(2026, 11, 1, 17, 30, tzinfo=IST)


def test_what_you_type_is_read_the_same_way():
    assert deadlines.parse_when("tomorrow", "18:00", NOW) == datetime(2026, 10, 28, 18, 0, tzinfo=IST)
    assert deadlines.parse_when("5 Nov", "6pm", NOW) == datetime(2026, 11, 5, 18, 0, tzinfo=IST)
    with pytest.raises(deadlines.DateNotUnderstood):
        deadlines.parse_when("someday", "", NOW)
    with pytest.raises(deadlines.DateNotUnderstood):
        deadlines.parse_when("2026-11-05", "half past six", NOW)


def mail(subject, text, labels=("INBOX",), received=NOW):
    return Mail("e1", "Devfolio", "team@devfolio.co", subject, received=received, text=text, labels=labels)


def test_a_deadline_is_found_in_an_email():
    found = deadlines.from_email(mail("Final reminder", "Hi! Submissions close on 30/10/2026 at 6 pm. Good luck."), NOW)
    assert found[0] == datetime(2026, 10, 30, 18, 0, tzinfo=IST) and "Submissions close" in found[1]


@pytest.mark.parametrize("subject,text,labels", [
    ("Big sale", "The sale ends tomorrow at midnight.", ("INBOX", "CATEGORY_PROMOTIONS")),
    ("Hello", "See you on 30/10/2026.", ("INBOX",)),  # a date, but not a deadline
    ("Old news", "The deadline was 01/10/2026.", ("INBOX",)),  # already passed
    ("Far away", "The deadline is 2027-12-01.", ("INBOX",)),  # more than 120 days ahead
])
def test_no_deadline_is_taken_from_offers_plain_dates_or_dates_out_of_range(subject, text, labels):
    assert deadlines.from_email(mail(subject, text, labels), NOW) is None


def test_reminders_come_3_days_1_day_and_3_hours_before_each_once(tmp_path):
    store = ProtectStore(tmp_path)
    due = NOW + timedelta(days=5)
    number = store.add_deadline("Hackathon submission", due, "you")
    titles = lambda moment: [f.title for f in deadlines.reminders(store, moment)]
    assert titles(NOW) == []
    assert titles(due - timedelta(hours=71)) == ["Due on Sun 1 Nov at 11:00 pm: Hackathon submission"]
    assert titles(due - timedelta(hours=70)) == []  # given once
    assert titles(due - timedelta(hours=23, minutes=30)) == ["Due tomorrow at 11:00 pm: Hackathon submission"]
    assert titles(due - timedelta(hours=2)) == ["Due today at 11:00 pm: Hackathon submission"]
    assert titles(due + timedelta(minutes=1)) == ["Deadline passed: Hackathon submission"]
    assert titles(due + timedelta(hours=1)) == [] and store.deadlines() == []
    findings = [f for f in deadlines.reminders(store, NOW)]
    assert findings == [] and number == 1


def test_after_the_pc_was_off_only_the_reminder_that_applies_now_comes(tmp_path):
    store = ProtectStore(tmp_path)
    due = NOW + timedelta(days=5)
    store.add_deadline("Report", due, "you")
    found = deadlines.reminders(store, due - timedelta(hours=2))
    assert [f.title for f in found] == ["Due today at 11:00 pm: Report"] and found[0].key.endswith(":3")


def test_a_deadline_due_tomorrow_says_tomorrow(tmp_path):
    store = ProtectStore(tmp_path)
    store.add_deadline("Hackathon submission", datetime(2026, 10, 28, 18, 0, tzinfo=IST), "you")
    found = deadlines.reminders(store, NOW)
    assert found[0].title == "Due tomorrow at 6:00 pm: Hackathon submission"
    assert found[0].classification == "Confirmed fact" and found[0].severity == "warning"


def test_an_email_deadline_is_labelled_as_read_from_the_email(tmp_path):
    store = ProtectStore(tmp_path)
    store.add_deadline("Final reminder", NOW + timedelta(hours=20), "email", "gmail:e1", "Submissions close tomorrow.")
    found = deadlines.reminders(store, NOW)
    assert found[0].classification == "Unknown" and "read this date from an email" in found[0].why[0]
    assert store.add_deadline("Final reminder", NOW + timedelta(hours=20), "email", "gmail:e1") is None  # once per email


def test_a_senders_second_reminder_email_does_not_add_the_same_deadline_twice(tmp_path):
    store = ProtectStore(tmp_path)
    due = NOW + timedelta(days=4)
    sentence = "Last date for exam fee - 01 November 2026 (up to 11:50 pm)"
    assert store.add_deadline("[Reminder-1]: Last date for exam registration", due, "email", "gmail:a", sentence)
    assert store.add_deadline("[Reminder-2]: Last date for exam registration", due, "email", "gmail:b", "other words") is None
    assert store.add_deadline("Exam fee", due, "email", "gmail:c", sentence) is None  # same sentence
    assert store.add_deadline("Hackathon results", due, "email", "gmail:d", "Results on 1 Nov")  # another deadline
    assert store.add_deadline("[Reminder-1]: Last date for exam registration", due + timedelta(days=1), "email", "gmail:e")
    assert len(store.deadlines()) == 3
