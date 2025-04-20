import asyncio
import logging
import slixmpp
from slixmpp.exceptions import IqError, IqTimeout

class XMPPTools(slixmpp.ClientXMPP):
	def __init__(self, jid, password, muc_jids, nick):
		slixmpp.ClientXMPP.__init__(self, jid, password)

		self.muc_jids = muc_jids
		self.nick = nick

		self.add_event_handler("session_start", self.start)
		self.add_event_handler("groupchat_message", self.muc_message)
		self.add_event_handler("message", self.dm_message)

		self.register_plugin('xep_0030')  # Service Discovery
		self.register_plugin('xep_0045')  # Multi-User Chat
		self.register_plugin('xep_0199')  # XMPP Ping

		self.commands = {
			'help': self.cmd_help,
			'version': self.cmd_version,
			'items': self.cmd_items,
			'contact': self.cmd_contact
		}

	async def start(self, event):
		self.send_presence()
		await self.get_roster()
		for muc_jid in self.muc_jids:
			self.plugin['xep_0045'].join_muc(muc_jid, self.nick)

	async def muc_message(self, msg):
		if msg['mucnick'] != self.nick and msg['body'].startswith('!xmpp'):
			response = await self.handle_command(msg['body'])
			self.send_message(mto=msg['from'].bare, mbody=response, mtype='groupchat')

	async def dm_message(self, msg):
		if msg['type'] in ('chat', 'normal') and msg['body'].startswith('!xmpp'):
			response = await self.handle_command(msg['body'])
			msg.reply(response).send()

	async def handle_command(self, body):
		parts = body.split(' ', 2)
		if len(parts) < 2 or not parts[1].strip():
			return "Use \"!xmpp help\" to list all commands."
		command = parts[1].strip()
		if command in self.commands:
			return await self.commands[command](parts)
		else:
			return f"Unknown command. Use \"!xmpp help\" to list all commands."

	async def cmd_help(self, parts):
		return "Available commands:\n!xmpp version - shows the version of an XMPP service.\n!xmpp items - shows the items of an XMPP service.\n!xmpp contact - shows the contact information of an XMPP service.\n!xmpp help - displays this message."

	async def cmd_version(self, parts):
		if len(parts) < 3 or not parts[2].strip():
			response = "!xmpp version - shows the version of an XMPP service.\nUsage: !xmpp version <service>"
		else:
			server = parts[2].strip()
			try:
				version_info = await self.get_service_version(server)
				response = f"{server} is running {version_info['name']} {version_info['version']}."
				if version_info['os']:
					response = f"{server} is running {version_info['name']} {version_info['version']} on {version_info['os']}."
			except (IqError, IqTimeout) as e:
				response = f"Could not retrieve version for {server}: {e}"
		return response

	async def cmd_items(self, parts):
		if len(parts) < 3 or not parts[2].strip():
			return "!xmpp items - shows the items of an XMPP service.\nUsage: !xmpp items <service>"
		service = parts[2].strip()
		try:
			items = await self.get_service_items(service)
			if items:
				response = f"Items for service {service}:\n"
				response += "\n".join([f"{item['jid']}" + (f" - {item['name']}" if item['name'] else "") for item in items])
			else:
				response = f"No items found for service {service}."
		except (IqError, IqTimeout) as e:
			response = f"Could not retrieve items for {service}: {e}"
		return response

	async def cmd_contact(self, parts):
		if len(parts) < 3 or not parts[2].strip():
			return "!xmpp contact - shows the contact information of an XMPP service.\nUsage: !xmpp contact <service>"
		service = parts[2].strip()
		try:
			contact_info = await self.get_service_contact_info(service)
			if contact_info:
				response = f"Contact information for service {service}:\n"
				for field, values in contact_info.items():
					if values:
						field_name = field.replace('-addresses', '').replace('-', ' ').title().strip()
						response += f"\n{field_name}:\n"
						response += "\n".join([f"  - {value}" for value in values])
						response += "\n"
			else:
				response = f"No contact information found for service {service}."
		except (IqError, IqTimeout) as e:
			response = f"Could not retrieve contact information for {service}: {e}"
		return response

	async def get_service_version(self, server):
		iq = self.Iq()
		iq['type'] = 'get'
		iq['to'] = server
		iq['id'] = 'version_1'
		iq['query'] = 'jabber:iq:version'

		result = await iq.send()
		query = result.xml.find('{jabber:iq:version}query')
		return {
			'name': query.findtext('{jabber:iq:version}name'),
			'version': query.findtext('{jabber:iq:version}version'),
			'os': query.findtext('{jabber:iq:version}os')
		}

	async def get_service_items(self, service):
		disco = self.plugin['xep_0030']
		items = await disco.get_items(jid=service)
		return items['disco_items']

	async def get_service_contact_info(self, service):
		iq = self.Iq()
		iq['type'] = 'get'
		iq['to'] = service
		iq['id'] = 'disco_info_1'
		iq['query'] = 'http://jabber.org/protocol/disco#info'

		result = await iq.send()
		query = result.xml.find('{http://jabber.org/protocol/disco#info}query')
		contact_info = {}
		for x in query.findall('{jabber:x:data}x'):
			if x.get('type') == 'result':
				for field in x.findall('{jabber:x:data}field'):
					var = field.get('var')
					if var in ['abuse-addresses', 'admin-addresses', 'feedback-addresses', 'sales-addresses', 'security-addresses', 'status-addresses', 'support-addresses']:
						contact_info[var] = [value.text for value in field.findall('{jabber:x:data}value')]
		return contact_info

if __name__ == '__main__':
	logging.basicConfig(level=logging.INFO)
	logging.getLogger('slixmpp').setLevel(logging.INFO)
	logging.getLogger('root').setLevel(logging.ERROR)

	jid = input("Bot's JID: ")
	password = input("Bot's Password: ")
	muc_jids = input("Space Delimited MUC JID's: ")
	mucs = []
	try:
		for x in muc_jids.split(' '):
			mucs.append(x)
	except:
		if not " " in muc_jids:
			mucs = [str(muc_jids)]
	muc_jids = mucs
	nick = input("Bot's Nickname: ")

	xmpp = XMPPTools(jid, password, muc_jids, nick)
	xmpp.connect()
	xmpp.process(forever=True)
