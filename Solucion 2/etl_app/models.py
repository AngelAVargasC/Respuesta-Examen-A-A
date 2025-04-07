from django.db import models

class Alarm(models.Model):
    alarm_occurred_on = models.DateTimeField(null=True, blank=True)
    alarm_cleared_on = models.DateTimeField(null=True, blank=True)
    alarm_source = models.CharField(max_length=255)
    alarm_name = models.CharField(max_length=255)
    region = models.CharField(max_length=100)
    site_parsed_alarm = models.CharField(max_length=100)

class Outage(models.Model):
    outage_occurred_on = models.DateTimeField(null=True, blank=True)
    outage_cleared_on = models.DateTimeField(null=True, blank=True)
    mo_name = models.CharField(max_length=255)
    outage_name = models.CharField(max_length=255)
    site_parsed_outage = models.CharField(max_length=100)

class JoinedRecord(models.Model):
    alarm_occurred_on = models.DateTimeField(null=True, blank=True)
    alarm_cleared_on = models.DateTimeField(null=True, blank=True)
    alarm_source = models.CharField(max_length=255)
    alarm_name = models.CharField(max_length=255)
    region = models.CharField(max_length=100)
    site_parsed_alarm = models.CharField(max_length=100)
    outage_occurred_on = models.DateTimeField(null=True, blank=True)
    outage_cleared_on = models.DateTimeField(null=True, blank=True)
    mo_name = models.CharField(max_length=255)
    outage_name = models.CharField(max_length=255)
    site_parsed_outage = models.CharField(max_length=100)
    battery_backup_time = models.CharField(max_length=100, blank=True)
    backup_minutes = models.FloatField(null=True, blank=True)