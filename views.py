# This is Django view.
#
# See: https://docs.djangoproject.com/en/1.3/topics/http/views/

import os
from vorostat.models import Channel, Message
from django.shortcuts import render_to_response, get_object_or_404
from django.db.models import Count
from django.db import connection, transaction
cursor = connection.cursor()
os.environ['MPLCONFIGDIR'] = "/home/vorostat/mpl/"
from pylab import *
from numpy import *
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from django.views.decorators.cache import cache_page

IMAGEPATH = "/home/vorostat/media/"
IMAGEURL = "http://pwnagedeluxe.nl/ircstats/media/"

# Define an overall color palette, consisting of 8 colors
PALETTE = ('#FF0D00', '#FF7A73', '#9BED00', '#C7F66F', '#03899C', '#5FC0CE', '#00C618', '#008110') 

@cache_page(900) # cache for 15 minutes (also limited by settings.py CACHE values!)
def stats(request, channel):
  # Obtain the channel stats are being generated for
  try:
    channel = "#%s" % channel
    channel = get_object_or_404(Channel, name=channel)
  except Channel.DoesNotExist:
    raise Http404

  sections = []

  # --- Generate a general section with a top speakers pie diagram, a per speaker time-of-day barchart and an activity plot over days ---
  name = "general statistics"
  text = "In general, the activity division between speakers was as follows. <img> Individual speakers spent their time at these hours. <img> In which daytime is considered to start at 6:00 and end at 23:59. Over time, activity developed like this: <img> Note how this graph gets corrupted in the unthinkable event of bot failure."
  images = []

  # Obtain pairs of speakers and their lines during the whole day and during daytime
  # (6:00 - 23:59) only. By counting lines regardless of time first, it is made sure speakers
  # that only speak during day or nighttime are not skipped.
  raw = Message.objects.extra(where=['channel_id=%s'], params=[channel.id]).values('sender').annotate(Count('sender')).order_by('-sender__count')

  # Convert the database result into lists and a dictionary for later use
  speakers = []
  scores = []
  speakerscores = {}
  for pair in raw:
    speakers.append(pair['sender'])
    scores.append(pair['sender__count'])
    speakerscores[pair['sender']] = pair['sender__count']

  # Limit the display to 7 speakers and an 'others' category
  speakers = speakers[:7] + ["others"]
  scores = scores[:7] + [sum(scores[7:])]

  # Generate the pie chart
  fig = figure(1, figsize=(6,6))
  #ax = axes([0.1, 0.1, 0.8, 0.8])
  explode=[0.05 for i in range(len(scores))]
  pie(scores, explode=explode, labels=speakers, autopct='%1.1f%%', shadow=True, colors=PALETTE)
  title("%s activity" % channel.name, bbox={'facecolor':'1', 'pad':5})

  image = "%s-pie.png" % channel.name[1:]

  fig.savefig("%s%s" % (IMAGEPATH, image))
  close()

  images.append(image)

  # Construct a barchart for the individual speakers, now distinguishing between day and night
  # Obtain lines spoken during daytime (6:00 - 23:59)
  rawday = Message.objects.extra(where=['channel_id=%s', 'HOUR(`time`) BETWEEN %s AND %s'], params=[channel.id, 6, 23]).values('sender').annotate(Count('sender'))

  # Convert the result into a useful dictionary
  speakerscoresday = {}
  for pair in rawday:
    speakerscoresday[pair['sender']] = pair['sender__count']

  # Compute lines spoken by top 7 speakers during day/night
  scoresday = []
  scoresnight = []
  for speaker in speakers[:7]:
    if speaker in speakerscoresday: # There's a chance they only spoke at night!
      scoresday.append(speakerscoresday[speaker])
      scoresnight.append(speakerscores[speaker] - speakerscoresday[speaker])
    else:
      scoresday.append(0)
      scoresnight.append(speakerscores[speaker])

  ind = np.arange(7)  # the x locations for the groups
  width = 0.35       # the width of the bars

  fig = figure(1, figsize=(6,4))
  ax = fig.add_subplot(111)
  rects1 = ax.bar(ind, scoresday[:7], width, color=PALETTE[0])
  rects2 = ax.bar(ind+width, scoresnight[:7], width, color=PALETTE[2])

  ax.set_ylabel('lines')
  ax.set_title('lines spoken by speaker and day/night')
  ax.set_xticks(ind+width)
  ax.set_xticklabels(speakers[:7])

  ax.legend( (rects1[0], rects2[0]), ('day', 'night') )

  image = "%s-bar.png" % channel.name[1:]

  fig.savefig("%s%s" % (IMAGEPATH, image))
  close()

  images.append(image)

  # Generate a plot of the amount of lines spoken per recorder day
  # Since Django does not support a good way to obtain the information
  # through its model API, it will be by-passed
  cursor.execute("SELECT DATE(time), COUNT(*) FROM vorostat_message WHERE channel_id = %s GROUP BY DATE(time) ORDER BY time ASC", [channel.id])
  day_activity = cursor.fetchall()

  # Convert the results into usable lists for plotting, making sure dates with zero scores are accounted for
  dates_scores_dict = {}
  for pair in day_activity:
    dates_scores_dict[pair[0]] = pair[1]

  dates = []
  date_scores = []

  current_date = min(dates_scores_dict)
  end_date = max(dates_scores_dict)
  while current_date <= end_date:
    dates.append(current_date)
    if current_date in dates_scores_dict:
      date_scores.append(dates_scores_dict[current_date])
    else:
      date_scores.append(0)
    current_date += timedelta(days=1)

  # Generate the figure
  fig = figure(1, figsize=(6,4))
  ax = fig.add_subplot(111)
  ax.plot(dates, date_scores, '-o', color=PALETTE[4])

  months = mdates.MonthLocator()
  days = mdates.DayLocator()
  monthsFmt = mdates.DateFormatter('%B')

  ax.xaxis.set_major_locator(months)
  ax.xaxis.set_major_formatter(monthsFmt)
  ax.xaxis.set_minor_locator(days)
  ax.grid(True)
  fig.autofmt_xdate()

  ax.set_xlabel('days')
  ax.set_ylabel('lines')
  ax.set_title('lines spoken over past months')

  image = "%s-dateline.png" % channel.name[1:]

  fig.savefig("%s%s" % (IMAGEPATH, image))
  close()

  images.append(image)

  # Create the section object
  sections.append(Stat(name=name, text=text, images=images))

  # --- Add a games section, showing a popularity plot of various games being played. ---
  name = "games related"
  text = "Different games are being played by people joining %s. Over the past months, popularity measured by mentions was as follows. <img>" % channel.name
  images = []

  # Games popularity over time plot analogous to the speaker activity over time plot
  game_colors = {'l4d': PALETTE[0], 'sc2': PALETTE[2], 'tf2': PALETTE[4], 'aoe2': PALETTE[6]} # defines games too!
  fig = figure(1, figsize=(6,5))
  ax = fig.add_subplot(111)

  plots = []
  for game in game_colors:
    cursor.execute("SELECT DATE(time), COUNT(*) FROM vorostat_message WHERE channel_id = %s AND text LIKE %s GROUP BY DATE(time) ORDER BY time ASC", [channel.id, '%%%s%%' % game ])
    game_day_activity = cursor.fetchall()

    game_dates_scores_dict = {}
    for pair in game_day_activity:
      game_dates_scores_dict[pair[0]] = pair[1]

    game_dates = []
    game_date_scores = []

    current_date = min(dates_scores_dict) # plot lines over the same dates domain as the overall activity
    end_date = max(dates_scores_dict)
    while current_date <= end_date:
      game_dates.append(current_date)
      if current_date in game_dates_scores_dict:
        game_date_scores.append(game_dates_scores_dict[current_date])
      else:
        game_date_scores.append(0)
      current_date += timedelta(days=1)

    plots.append(ax.plot(game_dates, game_date_scores, '-', color=game_colors[game]))

  ax.xaxis.set_major_locator(months) # Re-use locators from earlier plot
  ax.xaxis.set_major_formatter(monthsFmt)
  ax.xaxis.set_minor_locator(days)
  ax.grid(True)
  fig.autofmt_xdate()

  ax.set_xlabel('days')
  ax.set_ylabel('mentions')
  ax.set_title('game mentions over past months')

  ax.legend(plots, game_colors.keys())

  image = "%s-gamelines.png" % channel.name[1:]

  fig.savefig("%s%s" % (IMAGEPATH, image))
  close()

  images.append(image)

  # Create the section object
  sections.append(Stat(name=name, text=text, images=images))

  # --- Last, add a person-specific section, showing bindi's sleeprhythm  ---
  name = "personal section"
  text = "For teenagers it is very important to maintain a healthy and consistent sleeping rhythm. Unfortunately, considering the gaming scene, this is not always the case. The next graph displays sleep patterns of a test sample, as monitored in %s. <img> This is calculated as follows. Bindi's first line between 6:00 and 17:59 is considered to be his wake-up time. His last line between 18:00 and 5:59 is then assumed time for bed. Unfortunately, for the sample under examination even these extreme limits do not always work out. The trend-line however is not significantly influenced by a minor amount of errors. Subtracting the two trend lines, an estimate can be given for the test sample's sleeptime. <img> Use the information wisely bindi! Fortunately, some people do lead a healthy life. 'A laugh is the best medicine', some people say. <img>" % channel.name
  images = []

  # Construct a plot of bindi's wake-up and bedtime times per day day
  cursor.execute("SELECT DATE(time), TIME(MIN(time)) FROM vorostat_message WHERE channel_id = %s AND sender = %s AND HOUR(time) >= %s AND HOUR(time) < %s GROUP BY DATE(time) ORDER BY time ASC", [channel.id, 'bindi', 6, 18])
  bindi_day_activity = cursor.fetchall()
  cursor.execute("SELECT DATE(time), TIME(MAX(time)) FROM vorostat_message WHERE channel_id = %s AND sender = %s AND HOUR(time) >= %s GROUP BY DATE(time) ORDER BY time ASC", [channel.id, 'bindi', 18])
  bindi_night_early_activity = cursor.fetchall()
  cursor.execute("SELECT DATE(time), TIME(MAX(time)) FROM vorostat_message WHERE channel_id = %s AND sender = %s AND HOUR(time) < %s GROUP BY DATE(time) ORDER BY time ASC", [channel.id, 'bindi', 6])
  bindi_night_late_activity = cursor.fetchall()

  # Convert the results into usable lists for plotting, this time ignoring data for which no times are known.
  # matplotlib can only work with datetime models, so a dummy date is added.
  bindi_dates_day = []
  bindi_dates_night = []
  bindi_date_wake = []
  bindi_date_sleep = []
  for pair in bindi_day_activity:
    bindi_dates_day.append(pair[0])
    bindi_date_wake.append(datetime(2000, 1, 1, pair[1].hour, pair[1].minute, pair[1].second))
  # A special consideration is necessary here. When bindi goes to bed after midnight, times belong to the day
  # after. This must be compensated for.
  bindi_night_late_dict = {}
  for pair in bindi_night_late_activity:
    bindi_night_late_dict[pair[0]-timedelta(days=1)] = datetime(2000, 1, 2, pair[1].hour, pair[1].minute, pair[1].second)
  for pair in bindi_night_early_activity:
    bindi_dates_night.append(pair[0])
    if pair[0] in bindi_night_late_dict:
      bindi_date_sleep.append(bindi_night_late_dict[pair[0]])
    else:
      bindi_date_sleep.append(datetime(2000, 1, 1, pair[1].hour, pair[1].minute, pair[1].second))  
  
  # Generate the figure
  fig = figure(1, figsize=(6,6))
  ax = fig.add_subplot(111)
  wakeplot = ax.plot(bindi_dates_day, bindi_date_wake, '-x', color=PALETTE[6])
  sleepplot = ax.plot(bindi_dates_night, bindi_date_sleep, '-x', color=PALETTE[7])

  # Add trendlines
  x = date2num(bindi_dates_day)
  y = date2num(bindi_date_wake)
  wake_fit_coef = polyfit(x, y, 3)
  wake_fit = poly1d(wake_fit_coef)
  ax.plot(x, wake_fit(x), "--", color=PALETTE[0])
  x = date2num(bindi_dates_night)
  y = date2num(bindi_date_sleep)
  sleep_fit_coef = polyfit(x, y, 3)
  sleep_fit = poly1d(sleep_fit_coef)
  ax.plot(x, sleep_fit(x), "--", color=PALETTE[4])

  hours = mdates.HourLocator()
  hoursFmt = mdates.DateFormatter('%H')

  ax.xaxis.set_major_locator(months) # Re-use locators from earlier plot
  ax.xaxis.set_major_formatter(monthsFmt)
  ax.xaxis.set_minor_locator(days)
  ax.yaxis.set_major_locator(hours)
  ax.yaxis.set_major_formatter(hoursFmt)
  ax.grid(True)
  fig.autofmt_xdate()

  ax.set_xlabel('days')
  ax.set_ylabel('hour')
  ax.set_title('bindi\'s wake-up / bedtimes over past months')

  ax.legend((wakeplot, sleepplot), ('wake-up', 'bed'))

  image = "%s-bindisleepline.png" % channel.name[1:]

  fig.savefig("%s%s" % (IMAGEPATH, image))
  close()

  images.append(image)

  # Generate a prediction for bindi's sleeping times by subtracting the previous trendlines.
  fig = figure(1, figsize=(6,4))
  ax = fig.add_subplot(111)

  sleeptime_fit_coef = sleep_fit_coef - wake_fit_coef
  sleeptime_fit = poly1d(sleeptime_fit_coef) * 24
  ax.plot(x, sleeptime_fit(x), "-", color=PALETTE[4]) # Plot over the trendlines' time domain

  y_majorLocator   = MultipleLocator(1)
  y_majorFormatter = FormatStrFormatter('%d')

  ax.xaxis.set_major_locator(months) # Re-use locators from earlier plot
  ax.xaxis.set_major_formatter(monthsFmt)
  ax.xaxis.set_minor_locator(days)
  ax.yaxis.set_major_locator(y_majorLocator)
  ax.yaxis.set_major_formatter(y_majorFormatter)
  ax.grid(True)
  fig.autofmt_xdate()

  ax.set_xlabel('days')
  ax.set_ylabel('hours')
  ax.set_title('bindi\'s estimated amount of sleep')

  image = "%s-bindisleepamountline.png" % channel.name[1:]

  fig.savefig("%s%s" % (IMAGEPATH, image))
  close()

  images.append(image)

  # Plot a polar graph showing the amount of times hyster spoke 'lol' at different hours
  cursor.execute("SELECT HOUR(time), COUNT(*) FROM vorostat_message WHERE channel_id = %s AND sender = %s AND text LIKE %s GROUP BY HOUR(time) ORDER BY HOUR(time) ASC", [channel.id, 'hyster^', '%%%s%%' % 'lol'])
  lol_activity = cursor.fetchall()

  # Convert the results into usable lists for plotting, making sure hours with zero scores are accounted for
  hours_lols_dict = {}
  for pair in lol_activity:
    hours_lols_dict[pair[0]] = pair[1]

  hours = range(12)
  hour_lols = []

  for hour in hours:
    lols = 0
    # Convert 24h format to 12h format, in order to resemble an actual clock
    if hour in hours_lols_dict:
      lols += hours_lols_dict[hour]
    if hour+12 in hours_lols_dict:
      lols += hours_lols_dict[hour+12]
    hour_lols.append(lols)

  # Generate the figure
  fig = figure(1, figsize=(6,6))
  ax = fig.add_axes([0.1, 0.1, 0.8, 0.8], polar=True)

  N = len(hours)
  theta = np.arange(0.0, 2*np.pi, 2*np.pi/N)

  # Polar plots run counter clockwise, starting at the far right. This must be compensated for.
  hours.reverse()
  switch_position = int(3./4.*len(hours)-1)
  hours = hours[switch_position:] + hours[:switch_position]
  hours[hours.index(0)] = 12
  labels = [str(hour) for hour in hours]
  hour_lols.reverse()
  # Bars are placed inbetween hours, not on hours themselves. Reversing as it's done now, makes the bars
  # appear between the wrong hour values. Hence, offsetting by 1 is necessary.
  hour_lols = hour_lols[switch_position+1:] + hour_lols[:switch_position+1]

  radii = hour_lols
  width = 2*np.pi/N
  bars = ax.bar(theta, radii, width=width, bottom=0.0)
  for hour, bar in zip(hours, bars):
    if hour % 2 == 0:
      bar.set_facecolor(PALETTE[2])
    else:
      bar.set_facecolor(PALETTE[3])

  ax.set_title('hyster\'s lolclock')
  #labels = hours[1:] + [len(hours)]
  #labels.reverse() # because of reversing hours_lols, hours doesn't represent actual hour values anymore. Instead it merely
  ax.set_thetagrids(range(0, 360, 360 / len(hours)), labels=labels)

  image = "%s-hysterclock.png" % channel.name[1:]

  fig.savefig("%s%s" % (IMAGEPATH, image))
  close()

  images.append(image)
  
  # Create the section object
  sections.append(Stat(name=name, text=text, images=images))

  # Set the latest update time
  channel.processed = datetime.now()
  channel.save()

  return render_to_response('stats.html', {
    'channel': channel,
    'sections': sections,
  })
  
# Use a class of objects for constructing different sections
class Stat(object):
  def __init__(self, **kwargs):
    self.name = kwargs['name']
    self.text = kwargs['text']
    self.images = kwargs['images']
  def content(self):
    content = "<p>%s</p>" % self.text
    for image in self.images:
      content = content.replace('<img>', '</p>\n<img src=%s%s>\n<p>' % (IMAGEURL, image), 1)
    return content
