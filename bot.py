import socket, sys, os, re, random
from datetime import datetime
# Take care of Django database initialization
sys.path.append('/home/vorostat/vs_django')
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
#import settings
from vorostat.models import Channel, Message

# --- CUSTOMIZE BOT CONFIGURATION ---

# Set an admin password
ADMINPASS = "admin_pass"

# Customize CTCP version reply
CLIENTNAME = "Vorostat"
CLIENTVERSION = "1.0"
CLIENTENV = "Python2"

# Specify irc identity
DESIREDNICK = "HPBaxxter"
USERNAME = "hpbaxxter"
REALNAME = "Candyman, that's who I am."
QAUTHNAME = "HPBaxxter"
QAUTHPW = "q_auth_pw"

# ---

# Assist functions for retrieving the nickname and user@host from a prefix
def nick(prefix):
	return prefix.split("!")[0]
def hostmask(prefix):
	return prefix.split("!")[1]

class Bot(object):	
	# Object initialization
	def __init__(self):
		# Create a buffer for incoming commands as a string of lines and a buffer for outgoing commands as
		# a list
		self.in_buffer = ""
		self.out_buffer = []
		
		# Set some utility variables for properly processing the output buffer. 'BUFFER_RESERVE' is the
		# amount of bytes the program should reserve for the SPLIDGEPLOIT command, 'process_buffer' is used
		# for disabling/enabling buffer processing when the bytelimit is reached and 'bytes_sent' counts the
		# amount of bytes sent to the server.
		self.BUFFER_RESERVE = len("SPLIDGEPLOIT\r\n")
		self.process_buffer = True
		self.bytes_sent = 0
		
		# Create and connect socket
		self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.s.connect(("irc.quakenet.org", 6667))
		
		self.send("USER %s \"quakenet.org\" \"irc.quakenet.org\" :%s" % (USERNAME, REALNAME))
		self.send("NICK %s" % DESIREDNICK)
	
		# Create a dictionary for holding authnames
		self.auths = {}

	# Process data to be sent
	def process_output(self):
		# Iterate over the buffer until it is empty or the limit is reached
		while len(self.out_buffer) > 0 and self.process_buffer == True:
			# Take the oldest command
			line = "%s\r\n" % self.out_buffer[0]
			# See if sending the command would cross the limit. If so: do a check on the server's
			# buffer while disabling output in the meantime. If not: send the command.
			if self.bytes_sent + len(line) > 1024 - self.BUFFER_RESERVE:
				# Stop buffer processing
				self.process_buffer = False
				# Print the check command to the command prompt
				print "-> SPLIDGEPLOIT"
				# Send the check command
				self.s.send("SPLIDGEPLOIT\r\n")
			else:
				# Print the command to the command prompt and remove it from the buffer
				print "->", self.out_buffer.pop(0)
				# Send the command
				self.s.send(line)
				# Add the amount of sent bytes to the byte counter
				self.bytes_sent += len(line)
	
	# Buffer a command to be sent to the server
	def send(self, line):
		# Append the command to the end of the buffer 
		self.out_buffer.append(line)
	
	# Process data received
	def process_input(self):
		# Extend the input buffer with input from the socket
		self.in_buffer = self.in_buffer + self.s.recv(8192)
		# Create a list of commands to handle
		lines = self.in_buffer.split("\r\n")
		# Return the last, incomplete command to the buffer
		self.in_buffer = lines.pop(-1)
		
		# Handle the commands
		for line in lines:
			self.handle_line(line)
	
	# Handle single incoming commands
	def handle_line(self, line):
		# Print the line to the command prompt
		print "<-", line
		# Split up the command into recognizable pieces: "prefix", "command"
		# and "args". "args" is a list containing single words and possibly
		# a sentence last. The latter happens when the line contains a ":",
		# which is not added to "args".
		prefix = ''
		trailing = []
		if line[0] == ':':
			prefix, line = line[1:].split(' ', 1)
		if line.find(' :') != -1:
			line, trailing = line.split(' :', 1)
			args = line.split()
			args.append(trailing)
		else:
			args = line.split()
		command = args.pop(0)
		
		# Pass on commands for basic client operation
		BASE_COMMAND_HANDLERS = {
			"001": self.base_welcome_response,
			"376": self.base_end_of_motd_response,
			"421": self.base_unknown_command_response,
			"433": self.base_nick_taken_response,
			"NICK": self.base_nick_response,
			"PING": self.base_ping_response,
		}
		if command in BASE_COMMAND_HANDLERS:
			BASE_COMMAND_HANDLERS[command](prefix, command, args)
		
		# Pass on commands for bot specific operation
		BOT_COMMAND_HANDLERS = {
			"354": self.bot_who_reply_response,
			"366": self.bot_end_of_names_response,
			"396": self.bot_hidden_host_response,
			"JOIN": self.bot_join_response,
			"KICK": self.bot_kick_response,
			"PRIVMSG": self.bot_privmsg_response,
		}
		if command in BOT_COMMAND_HANDLERS:
			BOT_COMMAND_HANDLERS[command](prefix, command, args)
	
	# --- BASE COMMAND HANDLERS ---
	
	# Response to the IRCd welcome message
	def base_welcome_response(self, prefix, command, args):
		# Store the bot's initial nickname
		self.botnick = args[0]
	
	# Response to the "End of MOTD" message
	def base_end_of_motd_response(self, prefix, command, args):
		# Authenticate with the Q bot
		self.send("AUTH %s %s" % (QAUTHNAME, QAUTHPW))
		# Set the usermode for having a hidden hostmask
		self.send("MODE %s +x" % self.botnick)
	
	# Response to an "unknown command" message
	def base_unknown_command_response(self, prefix, command, args):
		# See if this message is resulting from a server buffer check and if so, re-enable
		# buffer processing
		if args[1] == "SPLIDGEPLOIT":
			# Reset the sent bytes counter
			self.bytes_sent = 0
			# Enable buffer processing
			self.process_buffer = True
	
	# Response to a "nickname taken" message
	def base_nick_taken_response(self, prefix, command, args):
		# Try to claim an alternative nickname
		self.send("NICK %s%c" % (args[1], random.choice("`_")))
	
	# Response to a nickname change
	def base_nick_response(self, prefix, command, args):
		# See if it is the bot who changed nickname and if so, update its stored nickname
		if nick(prefix) == self.botnick:
			# Update the stored bot nickname
			self.botnick = args[0]
	
	# Response to a ping request
	def base_ping_response(self, prefix, command, args):
		# Respond to the request
		self.send("PONG :%s" % args[0])
	
	# ------
	
	# --- BOT COMMAND HANDLERS ---

	# Response to a who reply
	def bot_who_reply_response(self, prefix, command, args):
		# Store the authname for a specific user@host
		self.auths["%s@%s" % (args[1], args[2])] = args[3]

	# Reponse to the "end of names" message
	def bot_end_of_names_response(self, prefix, command, args):
		# Request info on authnames on the channel
		self.send("WHO %s %%uha" % args[1])

	# Response to the "hidden host set" message
	def bot_hidden_host_response(self, prefix, command, args):
		# Join all stored channels
                channels = Channel.objects.filter(active=True)
		for channel in channels:
			self.send("JOIN %s" % channel)	
	
	# Response to a channel join
	def bot_join_response(self, prefix, command, args):
		# Make sure it is not the bot that is joining
		if nick(prefix) != self.botnick:
			# Request info on joined authname
			self.send("WHO %s n%%uha" % nick(prefix))

	# Response to a channel kick
	def bot_kick_response(self, prefix, command, args):
		# Check if the bot is being kicked from a channel and if so, make sure
		# it does not join again in the future.
		if args[1] == self.botnick:
                        channel = args[0]
                        delchans = Channel.objects.filter(name=channel)
                        if delchans:
                                delchan = delchans[0]
                                delchan.active = False
				delchan.save()

	# Response to a private message
	def bot_privmsg_response(self, prefix, command, args):
                # Check for a CTCP version request and if so respond
                if len(args) == 2 and args[1] == "\001VERSION\001":
                	self.send("NOTICE %s :\001VERSION %s:%s:%s\001" % 
				(nick(prefix), CLIENTNAME, CLIENTVERSION, CLIENTENV))
			return

		# Allow admins to make the bot join channels
		match = re.match("^%s join (\#[\w\.\-\_\'\`\^]+)$" % ADMINPASS, args[1])
		if match:
			channel = match.group(1)
			newchans = Channel.objects.filter(name=channel)
			if not newchans:
				newchan = Channel(name=channel, active=True, processed=datetime(2000, 1, 1))
				newchan.save()
				self.send("JOIN %s" % channel)
				self.send("PRIVMSG %s :OK, channel %s joined." % (nick(prefix), channel))
			else:
				newchan = newchans[0]
				if newchan.active == False:
					newchan.active = True
					newchan.save()
					self.send("JOIN %s" % channel)
                                	self.send("PRIVMSG %s :OK, channel %s joined." % (nick(prefix), channel))
			return

		# Let admins make the bot part channels
                match = re.match("^%s part (\#[\w\.\-\_\'\`\^]+)$" % ADMINPASS, args[1])
                if match:
                        channel = match.group(1)
                        delchans = Channel.objects.filter(name=channel)
			if delchans:
                                delchan = delchans[0]
                                delchan.active = False
				delchan.save()
                                self.send("PART %s" % channel)
                                self.send("PRIVMSG %s :OK, channel %s parted." % (nick(prefix), channel))
			return

		# Log a channel message
		if args[0][0] == '#':
			try:
				utext = args[1].decode('utf-8')
			except:
				utext = args[1].decode('iso-8859-1', 'replace')
			text = utext.encode('utf-8')
			channel = Channel.objects.get(name=args[0])
			msg = channel.message_set.create(
				time=datetime.now(), sender=self.auths[hostmask(prefix)], text=text)
			msg.save()

	# ------

# Main function taking care of initiating the bot and performing continuous operation
def main():
	bot = Bot()
	
	while True:
		bot.process_output()
		bot.process_input()

# Make this program useful as stand-alone too
if __name__ == "__main__":
	main()
