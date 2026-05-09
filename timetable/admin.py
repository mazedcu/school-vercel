from django.contrib import admin
from .models import TimeSlot, TimetableEntry

admin.site.register(TimeSlot)
admin.site.register(TimetableEntry)
