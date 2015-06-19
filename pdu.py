#!/usr/bin/env python


import os, os.path, sys
import time
import logging
import re
import ConfigParser
import argparse
from termcolor import colored
import sys
import copy
from pysnmp.entity.rfc3413.oneliner import cmdgen
from pysnmp.proto import rfc1902

# Nice logs:
os.environ['HAS_POWERLINE_FONT'] = "1"
from nicelog.formatters import ColorLineFormatter

from pprint import pprint



CONFIG_FILE = "~/.pdu_config.ini"


class Outlet():
	def __init__(self, _id):
		self._id = _id
		self.name = None
		self.status = None

	def setName(self, name):
		self.name = name.replace(" ", "-")

	def getName(self):
		return self.name

	def getId(self):
		return self._id

	def setStatus(self, s):
		if s == 1 or s == "ON":
			self.status = 1
		else:
			self.status = 0


	def isEnabled(self):
		return self.status > 0

	def getStatus(self):
		if self.isEnabled():
			return "ON"
		elif self.status is None:
			return "UNKNOWN"
		else:
			return "OFF"

	def __str__(self):
		return "Outlet #%s => %s is %s"%(self._id, self.name, self.getStatus())


class SnmpException(Exception): pass

class Pdu():
	TIMEOUT = 1
	def __init__(self, config, ip_or_id = None):
		self.config = config
		self.logger = logging.getLogger('pdu')
		self.outlets = {}
		self.cnf_outlets = {}
		self.amps = 0.0
		self._id = None
		self.infos = {}

		if ip_or_id is not None:
			try:
				self._id = int(ip_or_id)
				self._ip = None
				self.getConfigFromId()
			except ValueError:
				self._ip = ip_or_id
				self.setId()

			if config.has_section(self._ip):
				for item in config.items(self._ip):
					outlet = Outlet(self.getOutletId(item[0]))
					outlet.setName(self.getOutletName(item[0]))
					outlet.setStatus(item[1])
					self.outlets[outlet.getId()] = outlet


	def __str__(self):
		s = "Infos: \n"
		for k, v in self.infos.items():
			s += k + " = " + v + "\n"
		return str(s) # why need to cast with str() ??
	

	def getConfigFromId(self):
		for ip in self.config.sections():
			try:
				i = int(ip.split('.')[-1])
				if i == self._id:
					self._ip = ip
					self.logger.debug("Found IP %s from ID=%d", ip, self._id)
					break
			except: pass



	def fetchAndSave(self, out):
		self.fetchAll()
		self.save(out)


	def getIdFromOid(self, oid):
		return int(str(oid).split('.')[-1])


	def fetchAll(self,):
		self.logger.info("Fetch PDU %s configuration...", self._ip)
		self.fetchInfos()
		self.fetchNames()
		self.fetchStatus()
		self.fetchAmps()


	def fetchInfos(self):
		self.logger.debug("fetch infos")
		self.infos['name'] = self.snmpgetone(".1.3.6.1.2.1.1.5")
		self.infos['location'] = self.snmpgetone(".1.3.6.1.2.1.1.6")
		self.infos['version'] = self.snmpgetone(".1.3.6.1.4.1.318.1.1.4.1.2")
		self.infos['model'] = self.snmpgetone(".1.3.6.1.4.1.318.1.1.4.1.4")
		self.infos['sn'] = self.snmpgetone(".1.3.6.1.4.1.318.1.4.2.2.1.3")
		self.infos['md'] = self.snmpgetone(".1.3.6.1.4.1.318.1.1.12.1.4")


	def fetchNames(self,):
		self.logger.debug("fetch names")
		for varName in self.snmpget(".1.3.6.1.4.1.318.1.1.12.3.4.1.1.2."):
			for name, val in varName:
				outlet = Outlet(self.getIdFromOid(name))
				outlet.setName(str(val))
				self.logger.debug(outlet)
				self.outlets[outlet.getId()] = outlet


	def fetchStatus(self,):
		self.logger.debug("fetch status")
		for varStatus in self.snmpget(".1.3.6.1.4.1.318.1.1.12.3.3.1.1.4."):
			for name, val in varStatus:
				self.outlets[self.getIdFromOid(name)].setStatus(int(val))
		

	def getOutlet(self, outlet):
		if not self.outlets.has_key(outlet):
			self.fetchStatus()
		try:
			return self.outlets[outlet]
		except KeyError:
			return self.outlets[self.getOutletId(outlet)]


	def getOutletId(self, outlet):
		if type(outlet) == type(0):
			return outlet

		(outlet_id, outlet_name) = outlet.split('.')
		(prefix, oid) = outlet_id.split('_')
		return int(oid)


	def getOutletName(self, outlet):
		(outlet_id, outlet_name) = outlet.split('.')
		return outlet_name


	def setId(self):
		if self._id is None:
			self._id = int(str(self._ip).split('.')[-1])
		return self._id
	

	def fetchAmps(self):
		self.logger.debug("fetch amps")
		try:
			for varAmp in self.snmpget(".1.3.6.1.4.1.318.1.1.12.2.3.1.1.2"):
				for name, val in varAmp:
					if self.getIdFromOid(name) == 1:
						self.amps = float(val)/10
						self.logger.debug("Consumption: %.01fA", self.amps)
					else:
						self.logger.debug("Bank #%s : %sA", self.getIdFromOid(name), float(val)/10)

			self.logger.info("PDU#%d %s has %d outlets and current charging is %.01fA", self._id, self._ip, len(self.outlets), self.amps)
		except SnmpException:
			pass
			# log already dislayed fro self.snmpget()
			#self.logger.warning(ex)



	def snmpget(self, oid):
		errorIndication, errorStatus, errorIndex, varBinds = cmdgen.CommandGenerator().nextCmd(
			cmdgen.CommunityData('pypdu-agent', 'private', 0),
			cmdgen.UdpTransportTarget((self._ip, 161), timeout=self.TIMEOUT, retries=1),
			oid
		)
		if errorIndication:
			self.logger.critical(self._ip + ": " + str(errorIndication))
			raise SnmpException(errorIndication)
		else:
			if errorStatus:
				self.logger.critical('%s at %s' % (
						errorStatus.prettyPrint(),
						errorIndex and varBinds[int(errorIndex)-1][0] or '?'
					)
				)
				raise SnmpException(errorStatus.prettyPrint())
			else:
				return varBinds


	def snmpgetone(self, oid):
		for varName in self.snmpget(oid):
			for name, val in varName:
				return val


	def snmpset(self, oid, value):
		self.logger.debug("SNMP SET %s TO '%s'", oid, value)

		# Transform to RFC1902 format if not already
		if type(value) == type(1):
			value = rfc1902.Integer(value)
		elif type(value) == type(""):
			value = rfc1902.OctetString(value)
		# else: give directly the good RFC1902 type 

		errorIndication, errorStatus, errorIndex, varBinds = cmdgen.CommandGenerator().setCmd(
			cmdgen.CommunityData('pypdu-agent', 'private', 0),
			cmdgen.UdpTransportTarget((self._ip, 161), timeout=self.TIMEOUT*2, retries=4),
			(oid, value)
		)


	def save(self, outfile):
		self.config.remove_section(self._ip)
		self.config.add_section(self._ip)
		for outlet in self.outlets.values():
			self.config.set(self._ip, "outlet_%d.%s"%(outlet.getId(), outlet.getName()), outlet.getStatus())

		try:
			with open(outfile, "wb") as configfile:
				self.config.write(configfile)
				self.logger.info("Config successfully saved to %s", outfile)
		except:
			self.logger.critical("An error occured while writing to config file.", exc_info=True)



	def find(self, server):
		outlets = {}
		for ip in self.config.sections():
			for o in self.config.options(ip):
				(outlet, srv) = o.split('.')
				if server == srv:
					self.logger.info("%s found on %s => %s", server, ip, outlet)
					try:
						outlets[ip].append(o)
					except KeyError:
						outlets[ip] = [o]
		return outlets



	def power(self, action, outlet):
		if action in ("power-on", "ON"):
			statusid = 1
		elif action in ("power-off", "OFF"):
			statusid = 2
		elif action == "reboot":
			statusid = 3
		else:
			self.logger.critical("unknown action: '%s'", action)
			raise Exception("unknown action: '%s'"%action)

		try:
			oid = self.getOutletId(outlet)
		except:
			oid = None
			logging.error("Unable to found outlet ID for '%s' string, it must be 'outlet_5.something'", outlet)

		self.logger.info("%s : %s => %s", action.capitalize(), self._ip, self.getOutlet(outlet))

		if oid and statusid:
			self.snmpset(".1.3.6.1.4.1.318.1.1.12.3.3.1.1.4.%d" % oid, statusid)


	def applyConfig(self, ask=True):
		if not self.cnf_outlets:
			# backup outlets from config
			self.cnf_outlets = copy.deepcopy(self.outlets)

		if ask: # already fetched
			self.fetchNames()
			self.fetchStatus()

		something_to_do = False
		for outlet_id in self.cnf_outlets.keys():
			if self.cnf_outlets[outlet_id].getStatus() != self.outlets[outlet_id].getStatus():
				something_to_do = True
				self.logger.warning("Outlet %s is %s and will be set to %s", self.outlets[outlet_id].getName(), self.outlets[outlet_id].getStatus(), self.cnf_outlets[outlet_id].getStatus())
				if not ask:
					self.power(self.cnf_outlets[outlet_id].getStatus(), outlet_id)
			if self.cnf_outlets[outlet_id].getName() != self.outlets[outlet_id].getName():
				something_to_do = True
				self.logger.warning("Outlet %s will be renamed to %s", self.outlets[outlet_id].getName(), self.cnf_outlets[outlet_id].getName())
				if not ask:
					self.snmpset(".1.3.6.1.4.1.318.1.1.12.3.4.1.1.2.%d" % outlet_id, self.cnf_outlets[outlet_id].getName())
		
		if ask and something_to_do:
			answer = raw_input(colored("DO IT ? [yes|NO] ", "white", attrs=['bold']))
			self.logger.info("Replied: '%s'", answer.upper())
			if answer.upper() in ("Y", "YES"):
				self.applyConfig(ask=False)





#
# MAIN
#
if __name__ == '__main__':
	# setup logging
	logger = logging.getLogger('pdu')
	logger.setLevel(logging.DEBUG)
	handler = logging.StreamHandler(sys.stderr)
	handler.setFormatter(ColorLineFormatter(show_date=True, show_function=False, show_filename=False, message_inline=True))
	logger.addHandler(handler)

	# parser
	parser = argparse.ArgumentParser(description='PDU tool')
	parser.add_argument('--config', action='store', help='Config file, INI format')
	parser.add_argument('--debug', action='store_true', help='debug')
	parser.add_argument('--pdu', action='store', help='PDU id or IP address')
	parser.add_argument('--save', action='store_true', help='Save PDU informations to config file')
	parser.add_argument('--read', action='store_true', help='Read config file and push config to PDUs')
	parser.add_argument('--info', action='store_true', help='Display PDU informations')
	parser.add_argument('--amps', action='store_true', help='Display current charging per pdu')
	parser.add_argument('--on', action='store', help='Power ON this server')
	parser.add_argument('--off', action='store', help='Power OFF this server')
	parser.add_argument('--reboot', action='store', help='REBOOT this server')
	args = parser.parse_args()

	if args.debug:
		logger.setLevel(logging.DEBUG)
	else:
		logger.setLevel(logging.INFO)
	
	# config
	config = ConfigParser.ConfigParser()
	configfile = os.path.expanduser(CONFIG_FILE)
	if args.config:
		if not os.path.exists(os.path.abspath(args.config)):
			logger.warning("Create an empty config file")
			try:
				with open(os.path.abspath(os.path.expanduser(args.config)), 'w') as inifile:
					inifile.write()
					inifile.close()
			except:
				logger.critical("Unable to write to '%s'", args.config, exc_info=True)
		logger.debug("%s => %s", os.path.abspath(os.path.expanduser(args.config)), configfile)
		try:
			os.unlink(configfile)
		except: pass
		os.symlink(os.path.abspath(args.config), configfile)
		configfile = os.path.abspath(os.path.expanduser(args.config))

	logger.debug("Read config file: %s", configfile)
	config.read(configfile)

	if args.save:
		if not args.pdu:
			logger.critical("No pdu to connect to. Use -pdu IP parameter.")
			parser.print_help()
			sys.exit(1)

		pdu = Pdu(config, args.pdu)
		pdu.fetchAndSave(configfile)

	elif args.amps:
		 for pduip in config.sections():
			pdu = Pdu(config, pduip)
			try:
				#pdu.fetchNames()
				pdu.fetchAmps()
			except SnmpException: pass

	elif args.info and args.pdu:
		pdu = Pdu(config, args.pdu)
		pdu.fetchInfos()
		pdu.fetchNames()
		pdu.fetchStatus()
		print pdu
		for outlet in pdu.outlets.values():
			print outlet
			
	elif args.on or args.off or args.reboot:
		server = args.on or args.off or args.reboot
		if args.on:
			action = "power-on"
		elif args.off:
			action = "power-off"
		elif args.reboot:
			action = "reboot"

		pdu = Pdu(config)
		outlets = pdu.find(server)

		if len(outlets) > 0:
			msg = "Server '%s' found on %d outlets:\n"%(server, len(outlets))
			for o in outlets.keys():
				for oname in outlets[o]:
					olet = Pdu(config, o).getOutlet(oname)
					if olet.isEnabled():
						ostatus = colored(olet.getStatus(), 'green', attrs=['bold'])
					else:
						ostatus = colored(olet.getStatus(), 'red', attrs=['bold'])
					msg += colored("- %s => %s is "%(o, oname), "magenta", attrs=['bold'])
					msg += ostatus + "\n"
			print msg
			answer = raw_input(colored("If you want to ", "white", attrs=['bold']) + colored(action.upper(), "red", attrs=['bold']) + colored(", type ", "white", attrs=['bold']) + colored("YES", "green", attrs=['bold']) + colored(" : ", "white", attrs=['bold']))
			logger.debug("Response: '%s'", answer)
			if answer.upper() == 'YES':
				for pduip in outlets.keys():
					pdu = Pdu(config, pduip)
					for outlet in outlets[pduip]:
						pdu.power(action, outlet)

				if args.on or args.off:
					time.sleep(4)
					pdu.fetchStatus()
					pdu.save(configfile)

		else:
			print colored("Server '%s' not found"%server, 'yellow', 'on_red')

	elif args.read:
		if args.pdu:
			Pdu(config, args.pdu).applyConfig()
		else:
			for ip in config.sections():
				Pdu(config, ip).applyConfig()

