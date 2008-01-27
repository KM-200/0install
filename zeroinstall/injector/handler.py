"""
Integrates download callbacks with an external mainloop.
While things are being downloaded, Zero Install returns control to your program.
Your mainloop is responsible for monitoring the state of the downloads and notifying
Zero Install when they are complete.

To do this, you supply a L{Handler} to the L{policy}.
"""

# Copyright (C) 2006, Thomas Leonard
# See the README file for details, or visit http://0install.net.

import os, sys
from logging import debug, info, warn

from zeroinstall.support import tasks
from zeroinstall.injector import model, download
from zeroinstall.injector.iface_cache import iface_cache

class Handler(object):
	"""
	This implementation of the handler interface uses the GLib mainloop.

	@ivar monitored_downloads: dict of downloads in progress
	@type monitored_downloads: {URL: (error_stream, L{download.Download})}
	"""

	__slots__ = ['monitored_downloads', '_loop', '_loop_errors']

	def __init__(self, mainloop = None):
		self.monitored_downloads = {}		
		self._loop = None
		self._loop_errors = None
	
	def monitor_download(self, dl):
		"""Called when a new L{download} is started.
		This is mainly used by the GUI to display the progress bar."""
		dl.start()
		self.monitored_downloads[dl.url] = dl
		self.downloads_changed()

		def download_done():
			yield dl.downloaded
			del self.monitored_downloads[dl.url]
			self.downloads_changed()
		monitor = tasks.Task(download_done(), "download monitor")
	
	def downloads_changed(self):
		# This is just for the GUI to override
		pass
	
	def wait_for_blocker(self, blocker):
		if not blocker.happened:
			import gobject

			def quitter():
				yield blocker
				self._loop.quit()
			quit = tasks.Task(quitter(), "quitter")

			assert self._loop is None	# Avoid recursion
			self._loop = gobject.MainLoop(gobject.main_context_default())
			try:
				debug("Entering mainloop, waiting for %s", blocker)
				self._loop.run()
			finally:
				self._loop = None

			assert blocker.happened, "Someone quit the main loop!"

		tasks.check(blocker)
	
	def get_download(self, url, force = False):
		"""Return the Download object currently downloading 'url'.
		If no download for this URL has been started, start one now (and
		start monitoring it).
		If the download failed and force is False, return it anyway.
		If force is True, abort any current or failed download and start
		a new one.
		@rtype: L{download.Download}
		"""
		try:
			e, dl = self.monitored_downloads[url]
			if dl and force:
				dl.abort()
				raise KeyError
		except KeyError:
			dl = download.Download(url)
			self.monitor_download(dl)
		return dl

	def confirm_trust_keys(self, interface, sigs, iface_xml):
		"""We don't trust any of the signatures yet. Ask the user.
		When done update the L{trust} database, and then call L{trust.TrustDB.notify}.
		@arg interface: the interface being updated
		@arg sigs: a list of signatures (from L{gpg.check_stream})
		@arg iface_xml: the downloaded data (not yet trusted)
		@return: a blocker, if confirmation will happen asynchronously, or None
		"""
		from zeroinstall.injector import trust, gpg
		assert sigs
		valid_sigs = [s for s in sigs if isinstance(s, gpg.ValidSig)]
		if not valid_sigs:
			raise model.SafeException('No valid signatures found. Signatures:' +
					''.join(['\n- ' + str(s) for s in sigs]))

		domain = trust.domain_from_url(interface.uri)

		print "\nInterface:", interface.uri
		print "The interface is correctly signed with the following keys:"
		for x in valid_sigs:
			print "-", x

		if len(valid_sigs) == 1:
			print "Do you want to trust this key to sign feeds from '%s'?" % domain
		else:
			print "Do you want to trust all of these keys to sign feeds from '%s'?" % domain
		while True:
			i = raw_input("Trust [Y/N] ")
			if not i: continue
			if i in 'Nn':
				raise model.SafeException('Not signed with a trusted key')
			if i in 'Yy':
				break
		for key in valid_sigs:
			print "Trusting", key.fingerprint, "for", domain
			trust.trust_db.trust_key(key.fingerprint, domain)

		trust.trust_db.notify()
	
	def report_error(self, exception):
		"""Report an exception to the user.
		@param exception: the exception to report
		@type exception: L{SafeException}
		@since: 0.25"""
		if self._loop_errors is None:
			warn("%s", exception)
		else:
			self._loop_errors.append(str(exception))
			info("%s", exception)	# (will get reported later)
