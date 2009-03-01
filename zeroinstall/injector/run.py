"""
Executes a set of implementations as a program.
"""

# Copyright (C) 2009, Thomas Leonard
# See the README file for details, or visit http://0install.net.

import os, sys
from logging import debug, info

from zeroinstall.injector.model import SafeException, EnvironmentBinding, ZeroInstallImplementation
from zeroinstall.injector.iface_cache import iface_cache

def do_env_binding(binding, path):
	"""Update this process's environment by applying the binding.
	@param binding: the binding to apply
	@type binding: L{model.EnvironmentBinding}
	@param path: the selected implementation
	@type path: str"""
	os.environ[binding.name] = binding.get_value(path,
					os.environ.get(binding.name, None))
	info("%s=%s", binding.name, os.environ[binding.name])

class Runner:
	"""Execute a program.
	@ivar dry_run: if True, just print a message about what would have happened
	@type dry_run: bool
	@ivar main: the name of the binary to run, or None to use the default
	@type main: str
	@ivar wrapper: a command to use to actually run the binary, or None to run the binary directly
	@type wrapper: str
	@since 0.39"""
	dry_run = False
	main = None
	wrapper = None

	def run(self, selections, prog_args):
		"""Execute program. On success, doesn't return. On failure, raises an Exception.
		Returns normally only for a successful dry run.
		@param selections: the selected versions
		@type selections: L{selections.Selections}
		@param prog_args: arguments to pass to the program
		@type prog_args: [str]
		@precondition: All implementations are in the cache.
		"""
		if self.sandbox:
			return self._run_in_sandbox(selections, prog_args)
		sels = selections.selections
		for selection in sels.values():
			_do_bindings(selection, selection.bindings)
			for dep in selection.dependencies:
				dep_impl = sels[dep.interface]
				if not dep_impl.id.startswith('package:'):
					_do_bindings(dep_impl, dep.bindings)

		root_impl = sels[selections.interface]
		self._execute(root_impl, prog_args)

	def _run_in_sandbox(self, selections, prog_args):
		import tempfile, fcntl
		tmp = tempfile.TemporaryFile(prefix = '0launch-sandbox')
		doc = selections.toDOM()
		doc.writexml(tmp, encoding = 'utf-8')
		tmp.flush()
		tmp.seek(0)

		fcntl.fcntl(tmp, fcntl.F_SETFD, 0)	# close-on-exec = False

		if self.wrapper:
			launch_opts = ['--wrapper', self.wrapper]
		else:
			launch_opts = []

		prog_args = ['-c', self.sandbox + ' "$@"', '-',
				'0launch', '--set-selections-fd', str(tmp.fileno())] + launch_opts + ['--'] + list(prog_args)
		self._exec('/bin/sh', prog_args)

	def run_test(self, selections, prog_args):
		"""Run the program in a child process, collecting stdout and stderr.
		@return: the output produced by the process
		"""
		args = []
		import tempfile
		output = tempfile.TemporaryFile(prefix = '0launch-test')
		try:
			child = os.fork()
			if child == 0:
				# We are the child
				try:
					try:
						os.dup2(output.fileno(), 1)
						os.dup2(output.fileno(), 2)
						self.run(selections, prog_args)
					except:
						import traceback
						traceback.print_exc()
				finally:
					sys.stdout.flush()
					sys.stderr.flush()
					os._exit(1)

			info("Waiting for test process to finish...")

			pid, status = os.waitpid(child, 0)
			assert pid == child

			output.seek(0)
			results = output.read()
			if status != 0:
				results += "Error from child process: exit code = %d" % status
		finally:
			output.close()

		return results

	def _execute(self, root_impl, prog_args):
		assert root_impl is not None

		main = self.main

		if root_impl.id.startswith('package:'):
			main = main or root_impl.main
			prog_path = main
		else:
			if main is None:
				main = root_impl.main
			elif main.startswith('/'):
				main = main[1:]
			elif root_impl.main:
				main = os.path.join(os.path.dirname(root_impl.main), main)
			if main:
				prog_path = os.path.join(_get_implementation_path(root_impl.id), main)

		if main is None:
			raise SafeException("Implementation '%s' cannot be executed directly; it is just a library "
					    "to be used by other programs (or missing 'main' attribute)" %
					    root_impl)

		if not os.path.exists(prog_path):
			raise SafeException("File '%s' does not exist.\n"
					"(implementation '%s' + program '%s')" %
					(prog_path, root_impl.id, main))
		if self.wrapper:
			prog_args = ['-c', self.wrapper + ' "$@"', '-', prog_path] + list(prog_args)
			prog_path = '/bin/sh'

		self._exec(prog_path, prog_args)

	def _exec(self, prog_path, prog_args):
		if self.dry_run:
			print "Would execute:", prog_path, ' '.join(prog_args)
		else:
			info("Executing: %s", prog_path)
			sys.stdout.flush()
			sys.stderr.flush()
			try:
				os.execl(prog_path, prog_path, *prog_args)
			except OSError, ex:
				raise SafeException("Failed to run '%s': %s" % (prog_path, str(ex)))

def execute(policy, prog_args, dry_run = False, main = None, wrapper = None):
	"""@deprecated: see L{Runner.execute}"""
	from zeroinstall.injector import selections
	runner = Runner()
	runner.dry_run = dry_run
	runner.main = main
	runner.wrapper = wrapper
	runner.run(selections.Selections(policy), prog_args)

def execute_selections(selections, prog_args, dry_run = False, main = None, wrapper = None):
	"""@deprecated: see L{Runner.execute_selections}"""
	runner = Runner()
	runner.dry_run = dry_run
	runner.main = main
	runner.wrapper = wrapper
	runner.run(selections, prog_args)

def test_selections(selections, prog_args, dry_run, main, wrapper = None):
	"""@deprecated: see L{Runner.test_selections}"""
	runner = Runner()
	runner.dry_run = dry_run
	runner.main = main
	runner.wrapper = wrapper
	runner.run_test(selections, prog_args)

def _do_bindings(impl, bindings):
	for b in bindings:
		if isinstance(b, EnvironmentBinding):
			do_env_binding(b, _get_implementation_path(impl.id))

def _get_implementation_path(id):
	if id.startswith('/'): return id
	return iface_cache.stores.lookup(id)
