#!/usr/bin/python3 -u

import os
import signal
import sys
import xml.etree.ElementTree as ET
# import subprocess and osc_server (local file) conditionnally
# in order to answer faster in many cases.

OPERATION_TYPE_NULL = 0
OPERATION_TYPE_CONTROL = 1
OPERATION_TYPE_SERVER = 2
OPERATION_TYPE_SESSION = 3
OPERATION_TYPE_CLIENT = 4
OPERATION_TYPE_TRASHED_CLIENT = 5
OPERATION_TYPE_ALL = 6 # for help message

control_operations = ('start', 'start_new', 'stop', 'list_daemons', 'get_root', 
                      'get_port', 'get_port_gui_free', 'get_pid', 'get_session_path')

server_operations = (
    'quit', 'change_root', 'list_session_templates', 
    'list_user_client_templates', 'list_factory_client_templates', 
    'remove_client_template', 'list_sessions', 'new_session',
    'open_session', 'open_session_off', 'save_session_template',
    'rename_session', 'set_options',
    'script_info', 'script_user_action', 'hide_script_info',
    'has_attached_gui')

session_operations = ('save', 'save_as_template', 'take_snapshot',
                      'close', 'abort', 'duplicate', 'open_snapshot',
                      'rename', 'add_executable', 'add_proxy',
                      'add_client_template', 'list_snapshots',
                      'list_clients', 'list_trashed_clients',
                      'reorder_clients',
                      'get_session_name', 'process_step')

#client_operations = ('stop', 'kill', 'trash', 'resume', 'save',
                     #'save_as_template', 'show_optional_gui',
                     #'hide_optional_gui', 'update_properties',
                     #'list_snapshots', 'open_snapshot')

def signalHandler(sig, frame):
    if sig in (signal.SIGINT, signal.SIGTERM):
        global terminate
        terminate = True

def addSelfBinToPath():
    # Add raysession/src/bin to $PATH to can use ray executables after make
    # Warning, will works only if link to this file is in RaySession/*/*/*.py
    this_path = os.path.realpath(os.path.dirname(os.path.realpath(__file__)))
    bin_path = "%s/bin" % os.path.dirname(this_path)
    if not os.environ['PATH'].startswith("%s:" % bin_path):
        os.environ['PATH'] = "%s:%s" % (bin_path, os.environ['PATH'])

def pidExists(pid):
        if type(pid) == str:
            pid = int(pid)
        
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

def getDaemonList():
    try:
        tree = ET.parse('/tmp/RaySession/multi-daemon.xml')
    except:
        return []
    
    daemon_list = []
    has_dirty_pid = False
    
    root = tree.getroot()
    for child in root:
        daemon = Daemon()
        
        for key in child.attrib.keys():
            if key == 'root':
                daemon.root = child.attrib[key]
            elif key == 'session_path':
                daemon.session_path = child.attrib[key]
            elif key == 'user':
                daemon.user = child.attrib[key]
            elif key == 'not_default':
                daemon.not_default = bool(child.attrib[key] == '1')
            elif key == 'net_daemon_id':
                net_daemon_id = child.attrib[key]
                if net_daemon_id.isdigit():
                    daemon.net_daemon_id = int(net_daemon_id)
                    
            elif key == 'pid':
                pid = child.attrib[key]
                if pid.isdigit() and pidExists(pid):
                    daemon.pid = int(pid)
                    
            elif key == 'port':
                port = child.attrib[key]
                if port.isdigit():
                    daemon.port = int(port)
                    
            elif key == 'has_local_gui':
                daemon.has_local_gui = bool(child.attrib[key] == '1')
        
        if not (daemon.net_daemon_id
                and daemon.pid
                and daemon.port):
            continue
        
        daemon_list.append(daemon)
    return daemon_list

class Daemon:
    net_daemon_id = 0
    root = ""
    session_path = ""
    pid = 0
    port = 0
    user = ""
    not_default = False
    has_local_gui = False


def printHelp(stdout=False, category=OPERATION_TYPE_NULL):
    script_dir = os.path.dirname(os.path.realpath(sys.argv[0]))
    lang_file = "help_en_US"
    
    if os.getenv('LANG').startswith('fr_'):
        lang_file = "help_fr_FR"
        
    help_path = "%s/%s" % (script_dir, lang_file)
    
    try:
        help_file = open(help_path, 'r')
        full_message = help_file.read()
    except:
        sys.stderr.write('error: help_file %s is missing\n' % help_path)
        sys.exit(101)
    
    message = ''
    stars = 0
    
    if category == OPERATION_TYPE_ALL:
        message = full_message
    else:
        for line in full_message.split('\n'):
            if line.startswith('* '):
                stars+=1
            
            if (stars == 0
                    or (stars == 1 and category == OPERATION_TYPE_CONTROL)
                    or (stars == 2 and category == OPERATION_TYPE_SERVER)
                    or (stars == 3 and category == OPERATION_TYPE_SESSION)
                    or (stars >= 4 and category == OPERATION_TYPE_CLIENT)):
                message+= "%s\n" % line
        
    if stdout:
        sys.stdout.write(message)
    else:
        sys.stderr.write(message)

def autoTypeString(string):
    if string.isdigit():
        return int(string)
    elif string.replace('.', '', 1).isdigit():
        return float(string)
    return string
    
    
if __name__ == '__main__':
    addSelfBinToPath()
    
    if len(sys.argv) <= 1:
        printHelp()
        sys.exit(100)
    
    terminate = False
    operation_type = OPERATION_TYPE_NULL
    client_id = ''
    
    args = sys.argv[1:]
    
    wanted_port = 0
    detach = False
    
    dport = os.getenv('RAY_CONTROL_PORT')
    if dport and dport.isdigit():
        wanted_port = dport
    
    while args and args[0].startswith('--'):
        option = args.pop(0)
        
        if option.startswith('--help'):
            if option == '--help':
                printHelp(True, OPERATION_TYPE_NULL)
            elif option == '--help-all':
                printHelp(True, OPERATION_TYPE_ALL)
            elif option == '--help-control':
                printHelp(True, OPERATION_TYPE_CONTROL)
            elif option == '--help-server':
                printHelp(True, OPERATION_TYPE_SERVER)
            elif option == '--help-session':
                printHelp(True, OPERATION_TYPE_SESSION)
            elif option in ('--help-client', '--help-clients'):
                printHelp(True, OPERATION_TYPE_CLIENT)
            else:
                printHelp()
                sys.exit(100)
            sys.exit(0)
            
        elif option == '--port':
            if not args:
                printHelp()
                sys.exit(100)
            port = args.pop(0)
            if not port.isdigit():
                sys.stderr.write('Invalid value for port: %s . Use digits !'
                                 % port)
                sys.exit(100)
            wanted_port = int(port)
            
        elif option == '--detach':
            detach = True
    
    operation = args.pop(0)
    if operation in ('client', 'trashed_client'):
        if len(args) < 2:
            printHelp(False, OPERATION_TYPE_CLIENT)
            sys.exit(100)
        
        operation_type = OPERATION_TYPE_CLIENT
        if operation == 'trashed_client':
            operation_type = OPERATION_TYPE_TRASHED_CLIENT
        
        client_id = args.pop(0)
        operation = args.pop(0)
    
    if not operation_type:
        if operation in control_operations:
            operation_type = OPERATION_TYPE_CONTROL
        elif operation in server_operations:
            operation_type = OPERATION_TYPE_SERVER
        elif operation in session_operations:
            operation_type = OPERATION_TYPE_SESSION
        else:
            print('grkoto', operation)
            printHelp()
            sys.exit(100)
        
    arg_list = [autoTypeString(s) for s in args]
    if operation_type in (OPERATION_TYPE_CLIENT, 
                          OPERATION_TYPE_TRASHED_CLIENT):
        arg_list.insert(0, client_id)
    
    if operation in ('new_session', 'open_session', 'change_root',
                     'save_as_template', 'take_snapshot', 'duplicate',
                     'open_snapshot', 'rename', 'add_executable',
                     'add_client_template', 'script_info'):
        if not arg_list:
            sys.stderr.write('operation %s needs argument(s).\n' % operation)
            sys.exit(100)
    
    exit_code = 0
    daemon_announced = False
    
    daemon_list = getDaemonList()
    daemon_port = 0
    daemon_started = True
    
    for daemon in daemon_list:
        if (daemon.user == os.environ['USER']
                and not daemon.not_default):
            if not wanted_port or wanted_port == daemon.port:
                daemon_port = daemon.port
                break
    else:
        daemon_started = False
    
    if operation_type == OPERATION_TYPE_CONTROL:
        if operation == 'start':
            if daemon_started:
                sys.stderr.write('server already started.\n')
                sys.exit(0)
        
        elif operation == 'start_new':
            pass
        
        elif operation == 'stop':
            if not daemon_started:
                sys.stderr.write('No server started.\n')
                sys.exit(0)
        
        elif operation == 'list_daemons':
            for daemon in daemon_list:
                sys.stdout.write('%s\n' % str(daemon.port))
            sys.exit(0)
        
        else:
            if not daemon_started:
                sys.stderr.write(
                    'No server started. So impossible to %s\n' % operation)
                sys.exit(100)
                
            if operation == 'get_pid':
                for daemon in daemon_list:
                    if daemon.port == daemon_port:
                        sys.stdout.write('%s\n' % str(daemon.pid))
                        sys.exit(0)
            
            elif operation == 'get_port':
                sys.stdout.write("%s\n" % str(daemon_port))
                sys.exit(0)
            
            elif operation == 'get_port_gui_free':
                for daemon in daemon_list:
                    if (daemon.user == os.environ['USER']
                            and not daemon.not_default
                            and not daemon.has_local_gui):
                        sys.stdout.write('%s\n' % daemon.port)
                        break
                sys.exit(0)
                    
            
            elif operation == 'get_root':
                for daemon in daemon_list:
                    if daemon.port == daemon_port:
                        sys.stdout.write('%s\n' % daemon.root)
                        sys.exit(0)
                
            elif operation == 'get_session_path':
                for daemon in daemon_list:
                    if daemon.port == daemon_port:
                        if not daemon.session_path:
                            sys.exit(1)
                        sys.stdout.write('%s\n' % daemon.session_path)
                        sys.exit(0)
                        
    elif not daemon_started:
        at_port = ''
        if daemon_port:
            at_port = "at port %i" % daemon_port
            
        if operation_type == OPERATION_TYPE_SERVER:
            if operation == 'quit':
                sys.stderr.write('No server %s to quit !\n' % at_port)
                sys.exit(0)
        
        elif operation_type == OPERATION_TYPE_SESSION:
            sys.stderr.write("No server started %s. So no session to %s\n"
                                 % (at_port, operation))
            sys.exit(100)
        elif operation_type == OPERATION_TYPE_CLIENT:
            sys.stderr.write("No server started %s. So no client to %s\n"
                                 % (at_port, operation))
            sys.exit(100)
        elif operation_type == OPERATION_TYPE_CLIENT:
            sys.stderr.write(
                "No server started %s. So no trashed client to %s\n"
                                 % (at_port, operation))
            sys.exit(100)
        else:
            printHelp()
            sys.exit(100)
                
    osc_order_path = '/ray/'
    if operation_type == OPERATION_TYPE_CLIENT:
        osc_order_path += 'client/'
    elif operation_type == OPERATION_TYPE_TRASHED_CLIENT:
        osc_order_path += 'trashed_client/'
    elif operation_type == OPERATION_TYPE_SERVER:
        osc_order_path += 'server/'
    elif operation_type == OPERATION_TYPE_SESSION:
        osc_order_path += 'session/'
        
    osc_order_path += operation
    
    if operation_type == OPERATION_TYPE_CONTROL and operation == 'stop':
        osc_order_path = '/ray/server/quit'
    
    import osc_server # see top of the file
    server = osc_server.OscServer(detach)
    server.setOrderPathArgs(osc_order_path, arg_list)
    daemon_process = None
    
    if daemon_started and not (operation_type == OPERATION_TYPE_CONTROL
                               and operation == 'start_new'):
        if (operation_type == OPERATION_TYPE_CONTROL
                and operation == 'stop'):
            daemon_port_list = []
            
            if wanted_port:
                daemon_port_list.append(wanted_port)
            else:
                for daemon in daemon_list:
                    if (daemon.user == os.getenv('USER')
                            and not daemon.not_default):
                        daemon_port_list.append(daemon.port)
            
            server.stopDaemons(daemon_port_list)
        else:
            server.setDaemonAddress(daemon_port)
            server.sendOrderMessage()
            
        if detach:
            sys.exit(0)
    else:        
        session_root = "%s/Ray Sessions" % os.getenv('HOME')
        try:
            settings_file = open("%s/.config/RaySession/RaySession.conf", 'r')
            contents = settings_file.read()
            for line in contents.split('\n'):
                if line.startswith('default_session_root='):
                    session_root = line.replace('default_session_root', '', 1)
                    break
        except:
            pass
        
        # start a daemon because no one is running
        import subprocess # see top of the file
        process_args = ['ray-daemon', '--control-url', str(server.url),
                        '--session-root', session_root]
        
        if wanted_port:
            process_args.append('--osc-port')
            process_args.append(str(wanted_port))
        
        daemon_process = subprocess.Popen(process_args,
            -1, None, None, subprocess.DEVNULL, subprocess.DEVNULL)
        
        server.waitForStart()
        
        if (operation_type == OPERATION_TYPE_CONTROL
                and operation in ('start', 'start_new')):
            server.waitForStartOnly()
    
    #connect SIGINT and SIGTERM
    signal.signal(signal.SIGINT,  signalHandler)
    signal.signal(signal.SIGTERM, signalHandler)
    
    exit_code = -1
    
    while True:
        server.recv(50)
        
        if terminate:
            break
        
        exit_code = server.finalError()
        if exit_code >= 0:
            break
        
        if server.isWaitingStartForALong():
            exit_code = 103
            break
        
        if daemon_process and not daemon_process.poll() is None:
            sys.stderr.write('daemon terminates, sorry\n')
            exit_code = 104
            break
    
    if (operation_type == OPERATION_TYPE_CONTROL
            and operation == 'start_new'
            and exit_code == 0):
        daemon_port = server.getDaemonPort()
        if daemon_port:
            sys.stdout.write("%i\n" % daemon_port)
    
    sys.exit(exit_code)
