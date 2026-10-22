import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from students.models import StudentProfile
from timetable.grid import build_grid, sorted_slots
from timetable.models import TimeSlot, TimetableEntry

PW = "pw-test-1"


def t(h, m=0):
    return datetime.time(h, m)


class TimetableBase(TestCase):
    def setUp(self):
        grade = ClassGroup.objects.create(name="Grade 9")
        self.sec_a = Section.objects.create(name="A", class_group=grade, academic_year="2026")
        self.sec_b = Section.objects.create(name="B", class_group=grade, academic_year="2026")
        self.math = Subject.objects.create(name="Math", code="M9")
        self.physics = Subject.objects.create(name="Physics", code="P9")
        self.admin = User.objects.create_user(username="adm", password=PW, role=User.Role.ADMIN)
        self.teacher = User.objects.create_user(username="tea", password=PW, role=User.Role.TEACHER)
        self.teacher2 = User.objects.create_user(username="tea2", password=PW, role=User.Role.TEACHER)
        self.coord = User.objects.create_user(username="coo", password=PW, role=User.Role.COORDINATOR)
        self.sun9 = TimeSlot.objects.create(day="sunday", start_time=t(9), end_time=t(9, 45))

    def entry(self, section, subject, teacher, slot, room=""):
        return TimetableEntry.objects.create(
            section=section, subject=subject, teacher=teacher, time_slot=slot, room=room)


class DayOrderAndGridTests(TimetableBase):
    def test_week_starts_saturday_and_sorts_by_day_not_alphabet(self):
        TimeSlot.objects.create(day="friday", start_time=t(9), end_time=t(9, 45))
        TimeSlot.objects.create(day="monday", start_time=t(9), end_time=t(9, 45))
        TimeSlot.objects.create(day="saturday", start_time=t(9), end_time=t(9, 45))
        self.assertEqual([s.day for s in sorted_slots()], ["saturday", "sunday", "monday", "friday"])

    def test_grid_marks_days_without_that_period(self):
        TimeSlot.objects.create(day="monday", start_time=t(9), end_time=t(9, 45))
        TimeSlot.objects.create(day="monday", start_time=t(10), end_time=t(10, 45))  # Monday only
        self.entry(self.sec_a, self.math, self.teacher, self.sun9)
        headers, rows = build_grid(TimetableEntry.objects.all())
        self.assertEqual([h["key"] for h in headers], ["sunday", "monday"])
        self.assertEqual(rows[0]["cells"][0]["subject"], "Math")
        self.assertIsNone(rows[1]["cells"][0]["slot"])       # no 10:00 period on Sunday
        self.assertIsNotNone(rows[1]["cells"][1]["slot"])

    def test_student_sees_sunday_classes(self):
        student = User.objects.create_user(username="stu", password=PW, role=User.Role.STUDENT)
        StudentProfile.objects.create(user=student, section=self.sec_a)
        self.entry(self.sec_a, self.math, self.teacher, self.sun9)
        self.client.login(username="stu", password=PW)
        r = self.client.get(reverse("my_timetable"))
        self.assertEqual([h["key"] for h in r.context["day_headers"]], ["sunday"])
        self.assertContains(r, "Math")

    def test_class_view_updates_immediately_after_delete(self):
        e = self.entry(self.sec_a, self.math, self.teacher, self.sun9)
        self.client.login(username="adm", password=PW)
        url = reverse("view_timetable") + f"?section={self.sec_a.id}"
        self.assertContains(self.client.get(url), "Math")
        e.delete()
        self.assertNotContains(self.client.get(url), "Math")


class ClashTests(TimetableBase):
    def test_teacher_clash_on_overlapping_but_different_slot(self):
        self.entry(self.sec_a, self.math, self.teacher, self.sun9)
        # A slot that overlaps 09:00–09:45 cannot exist for the same day…
        with self.assertRaises(ValidationError):
            TimeSlot(day="sunday", start_time=t(9, 30), end_time=t(10, 15)).full_clean()
        # …but if one was created before validation existed, the clash is still caught.
        overlapping = TimeSlot.objects.create(day="sunday", start_time=t(9, 30), end_time=t(10, 15))
        with self.assertRaisesMessage(ValidationError, "already teaches Grade 9 – A"):
            self.entry(self.sec_b, self.physics, self.teacher, overlapping)

    def test_section_clash_on_overlapping_slot(self):
        self.entry(self.sec_a, self.math, self.teacher, self.sun9)
        overlapping = TimeSlot.objects.create(day="sunday", start_time=t(9, 30), end_time=t(10, 15))
        with self.assertRaisesMessage(ValidationError, "This section already has Math"):
            self.entry(self.sec_a, self.physics, self.teacher2, overlapping)

    def test_room_clash_ignores_case_and_spaces(self):
        self.entry(self.sec_a, self.math, self.teacher, self.sun9, room="Room 101")
        with self.assertRaisesMessage(ValidationError, "Room Room 101 is already used"):
            self.entry(self.sec_b, self.physics, self.teacher2, self.sun9, room="  room 101 ")

    def test_back_to_back_periods_do_not_clash(self):
        self.entry(self.sec_a, self.math, self.teacher, self.sun9)
        next_slot = TimeSlot.objects.create(day="sunday", start_time=t(9, 45), end_time=t(10, 30))
        self.entry(self.sec_b, self.math, self.teacher, next_slot)  # no error

    def test_coordinator_can_be_scheduled_but_student_cannot(self):
        self.entry(self.sec_a, self.math, self.coord, self.sun9)
        student = User.objects.create_user(username="stu", password=PW, role=User.Role.STUDENT)
        with self.assertRaisesMessage(ValidationError, "Only teachers and coordinators"):
            self.entry(self.sec_b, self.math, student, self.sun9)

    def test_end_time_must_be_after_start(self):
        with self.assertRaisesMessage(ValidationError, "End time must be after start time"):
            TimeSlot(day="monday", start_time=t(10), end_time=t(9)).full_clean()


class RoutineEditorTests(TimetableBase):
    def setUp(self):
        super().setUp()
        self.client.login(username="adm", password=PW)

    def save(self, **data):
        base = {"section": self.sec_a.id, "slot": self.sun9.id, "subject": self.math.id,
                "teacher": self.teacher.id, "room": ""}
        base.update(data)
        return self.client.post(reverse("timetable_save_entry"), base)

    def test_editor_page_renders_grid_for_section(self):
        self.entry(self.sec_a, self.math, self.teacher, self.sun9)
        r = self.client.get(reverse("timetable_gen") + f"?section={self.sec_a.id}")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="tt-btn has-class"')
        self.assertContains(r, "(Coordinator)")
        self.assertEqual(r.context["scheduled_count"], 1)

    def test_add_periods_on_many_days_and_skip_existing(self):
        r = self.client.post(reverse("timetable_gen"), {
            "action": "add_periods", "section": self.sec_a.id,
            "days": ["sunday", "monday", "tuesday"],
            "start_time": ["09:00", "09:45"], "end_time": ["09:45", "10:30"],
        })
        self.assertRedirects(r, reverse("timetable_gen") + f"?section={self.sec_a.id}",
                             fetch_redirect_response=False)
        # 3 days × 2 periods, minus Sunday 09:00 which already existed
        self.assertEqual(TimeSlot.objects.count(), 6)

    def test_add_periods_rejects_bad_times(self):
        self.client.post(reverse("timetable_gen"), {
            "action": "add_periods", "days": ["monday"],
            "start_time": ["10:00", "09:30"], "end_time": ["09:00", "10:30"],
        })
        self.assertEqual(TimeSlot.objects.filter(day="monday").count(), 1)  # only 09:30–10:30

    def test_create_update_and_delete_class(self):
        r = self.save()
        self.assertEqual(r.status_code, 200)
        cell = r.json()["cell"]
        self.assertEqual((cell["subject"], cell["teacher"]), ("Math", "tea"))

        r = self.save(entry=cell["entry_id"], subject=self.physics.id, room="Lab")
        self.assertEqual(r.json()["cell"]["subject"], "Physics")
        self.assertEqual(TimetableEntry.objects.count(), 1)

        r = self.client.post(reverse("timetable_delete_entry"), {"entry": cell["entry_id"]})
        self.assertTrue(r.json()["ok"])
        self.assertEqual(TimetableEntry.objects.count(), 0)

    def test_clash_returns_readable_error(self):
        self.entry(self.sec_b, self.physics, self.teacher, self.sun9)
        r = self.save()
        self.assertEqual(r.status_code, 409)
        self.assertIn("already teaches Grade 9 – B (Physics)", r.json()["error"])

    def test_slot_info_lists_busy_teachers_and_rooms_in_other_sections(self):
        self.entry(self.sec_b, self.physics, self.teacher, self.sun9, room="Lab")
        r = self.client.get(reverse("timetable_slot_info"),
                            {"slot": self.sun9.id, "section": self.sec_a.id})
        data = r.json()
        self.assertIn("Grade 9 – B", data["busy_teachers"][str(self.teacher.id)])
        self.assertIn("lab", data["busy_rooms"])
        # The section's own class is not reported as a clash
        r = self.client.get(reverse("timetable_slot_info"),
                            {"slot": self.sun9.id, "section": self.sec_b.id})
        self.assertEqual(r.json()["busy_teachers"], {})

    def test_delete_without_entry_is_a_clean_error(self):
        r = self.client.post(reverse("timetable_delete_entry"), {"entry": ""})
        self.assertEqual(r.status_code, 400)

    def test_non_admin_cannot_edit(self):
        self.client.login(username="tea", password=PW)
        r = self.save()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(TimetableEntry.objects.count(), 0)
