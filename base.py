#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = "duc_tin"

"""
    Manage basic setting and pre-run condition
"""

import configparser
import re
import sys, os, shutil
import socket
import datetime
import base64
from collections import OrderedDict
from subprocess import call, check_output
import json


def is_IF_ok():
    """ Check all interfaces if any of them is up and linked """
    ips = check_output(['hostname', '--all-ip-addresses']).strip()
    if not ips:
        return False
    else:
        for x in os.listdir("/sys/class/net/"):
            with open(f"/sys/class/net/{x}/operstate") as IF_state:
                if IF_state.read().strip() == "up":
                    return True
        else:
            return False


class Server:
    def __init__(self, data, mode='main'):
        self.mode = mode
        if mode == 'main':
            self.name = data[0]
            self.ip = data[1]
            self.score = int(data[2])
            self.ping = int(data[3]) if data[3] != '-' else 'inf'
            self.speed = int(data[4])
            self.country_long = data[5]
            self.country_short = data[6]
            self.NumSessions = data[7]
            self.uptime = data[8]
            self.logPolicy = "2wk" if data[11] == "2weeks" else "inf"
            self.config_data = str(base64.b64decode(data[-1]), 'ascii')
            self.proto = 'tcp' if '\r\nproto tcp\r\n' in self.config_data else 'udp'
            port = re.findall('remote .+ \d+', self.config_data)
            if not port:
                self.port = '1'
            else:
                self.port = port[0].split()[-1]

        else:
            self.name = data['name']
            self.ip = data['ip']
            self.port = data['port']
            self.proto = data['proto']
            self.country_short = data['country']
            self.description = data['description']
            self.path = data['path']


    def write_file(self, **kwargs):
        if self.mode=='main':
            txt_data = self.config_data
        else:
            with open(self.path) as fi:
                txt_data = ''.join(fi.readlines())

        use_proxy = kwargs.get('use_proxy', 'no')

        if use_proxy == 'yes':
            proxy = kwargs['proxy']
            port = kwargs['port']
            txt_data = txt_data.replace('\r\n;http-proxy-retry\r\n', '\r\nhttp-proxy-retry 3\r\n')
            txt_data = txt_data.replace('\r\n;http-proxy [proxy server] [proxy port]\r\n',
                                        '\r\nhttp-proxy %s %s\r\n' % (proxy, port))

        extra_option = ['keepalive 5 30\r\n',  # prevent connection drop due to inactivity timeout
                        'connect-retry 2\r\n']

        if 'keepalive 5 30' not in txt_data:
            index = txt_data.find('client\r\n')
            txt_data = txt_data[:index] + ''.join(extra_option) + txt_data[index:]

        path = kwargs.get('filename', '')
        path = 'vpn_tmp' if not path else path
        tmp_vpn = open(path, 'w+')
        tmp_vpn.write(txt_data)
        return tmp_vpn

    def __str__(self):
        if self.mode=='main':
            spaces = [5, 4, 5, 8, 12, 4, 8, 6, 16, 6]
            speed = self.speed / 1000. ** 2
            uptime = datetime.timedelta(milliseconds=int(self.uptime))
            uptime = re.split(',|\.', str(uptime))[0]
            txt = [self.country_short, str(self.ping), '%.2f' % speed, uptime, self.logPolicy, str(self.score), self.proto,
                   self.ip, self.port]
            txt = [dta.center(spaces[ind + 1]) for ind, dta in enumerate(txt)]
            return ''.join(txt)

        else:
            spaces = [15, 8, 6, 16, 6]
            line = [self.name, self.country_short, self.proto, self.ip, self.port]
            line = [str(x).center(spaces[i]) for i, x in enumerate(line)]
            line = ' '.join(line) + ' ' + self.description[0:22]
            return line


class Setting:
    def __init__(self):
        self.path = sys.argv[1] + '/.config/vpngate-with-proxy'
        self.config_file = self.path + '/config.ini'
        self.user_script_file = self.path + '/user_script.sh'
        self.favorites = self.path + '/favorites'
        self.parser = configparser.ConfigParser()

        # section network
        self.network = OrderedDict([('use_proxy', 'no'), ('address', ''), ('port', ''), ('ip', ''),
                                    ('test_interval', '0.25'), ('timeout', '1'),
                                    ('fix_dns', 'yes'), ('dns', '8.8.8.8, 84.200.69.80, 208.67.222.222'),
                                    ('disable_ipv6', 'yes'),
                                    ('mode', 'main')])

        # section filter
        self.filter = OrderedDict([('country', 'all'), ('port', 'all'), ('score', 'all'),
                                   ('proto', 'all'), ('sort_by', 'score')])

        # section log
        self.show_log = {'verbose': 'yes'}

        # section mirrors
        self.mirrors = {'url': "http://p76ed4cd5.tokynt01.ap.so-net.ne.jp:16169, "
                               "http://103.1.249.67:29858, "
                               "http://211.217.242.42:3230, "
                               "http://zp018093.ppp.dion.ne.jp:36205"}

        # section automation
        self.automation = OrderedDict([("activate", "yes"),
                                       ("fetch_interval", "1"),  # hour
                                       ])

        # config file's content
        self.sections = OrderedDict([('network', self.network),
                                     ('filter', self.filter),
                                     ('show_log', self.show_log),
                                     ('mirrors', self.mirrors),
                                     ('automation', self.automation)])

    def __getitem__(self, index):
        data = []
        for sec in self.sections.values():
            data += sec.values()

        return data[index]

    def write(self):
        for sect in self.sections:
            if not self.parser.has_section(sect):
                self.parser.add_section(sect)
            for content in self.sections[sect]:
                self.parser.set(sect, content, self.sections[sect][content])

        with open(self.config_file, 'w+') as configfile:
            self.parser.write(configfile)

    def load(self):
        self.parser.read(self.config_file)
        need_rewrite = False

        for sect in self.sections:
            for content in self.sections[sect]:
                try:
                    self.sections[sect][content] = self.parser.get(sect, content)
                except configparser.NoSectionError:
                    need_rewrite = True
                    self.parser.add_section(sect)
                except configparser.NoOptionError:
                    self.parser.set(sect, content, self.sections[sect][content])

        if need_rewrite:
            self.write()

    def check(self):
        # first time running check
        if not os.path.exists(self.config_file):
            self.create_new()

        # No symlink to current directory?
        if not os.path.exists("config.ini"):
            os.symlink(self.config_file, "config.ini")

        # No symlink of user_script found?
        if not os.path.exists("user_script.sh"):
            call(["cp", "user_script.sh.tmp", self.user_script_file])
            os.symlink(self.user_script_file, "user_script.sh")

        # No symlink of Favorites folder
        if not os.path.exists("favorites"):
            if not os.path.exists(self.favorites):
                os.mkdir(self.favorites)
            os.symlink(self.favorites, "favorites")

    def create_new(self):
        if not os.path.exists(self.path):
            os.makedirs(self.path)

        print('\n' + '_' * 12 + ctext(' First time config ', 'gB') + '_' * 12 + '\n')

        self.network['use_proxy'] = 'no' if input(ctext('Do you need proxy to connect? ', 'B') +
                                                  '(yes|[no]):') in 'no' else 'yes'

        if self.network['use_proxy'] == 'yes':
            proxy = port = ip = ''
            use_it = 'no'

            # try to detect proxy from current env
            for http_str in ["http_proxy", "HTTP_PROXY"]:
                if http_str in os.environ:
                    proxy, port = os.environ[http_str].strip('/').split('//')[1].split(':')
                    ip = socket.gethostbyname(proxy)
                    break

            if proxy:
                print(' You are using proxy: ' + ctext('%s:%s' % (proxy, port), 'pB'))
                use_it = 'yes' if input(
                    ctext(' Use this proxy? ', 'B') + '([yes]|no):') in 'yes' else 'no'

            if use_it == 'no':
                print(' Input your http proxy such as ' + ctext('www.abc.com:8080', 'pB'))
                while 1:
                    try:
                        proxy, port = input(' Your\033[95m proxy:port \033[0m: ').split(':')
                        ip = socket.gethostbyname(proxy)
                        port = port.strip()
                        if not 0 <= int(port) <= 65535:
                            raise ValueError
                    except ValueError:
                        print(ctext(' Error: Http proxy must in format ', 'r') + ctext('address:port', 'B'))
                        print(' Where ' + ctext('address', 'B') + ' is in form of www.abc.com or 123.321.4.5')
                        print('       ' + ctext('port', 'B') + ' is a number in range 0-65535')
                    else:
                        break

            self.network['address'] = proxy
            self.network['port'] = port
            self.network['ip'] = ip

        self.get_input()
        print('\n' + '_' * 12 + ctext(' Config done', 'gB') + '_' * 12 + '\n')

    def get_input(self):
        def allow_proxy(user_input='@'):
            while user_input.lower() not in ['y', 'n', 'yes', 'no']:
                user_input = input('Use proxy to connect to vpn? (yes|no): ')
            else:
                self.network['use_proxy'] = 'no' if user_input in 'no' else 'yes'

        def set_proxy_addr():
            self.network['address'] = input('Your http_proxy: ')
            try:
                self.network['ip'] = socket.gethostbyname(self.network['address'])
            except socket.gaierror:
                self.network['ip'] = ''
                print(" Can't resolve hostname of proxy, please input ip!")

        def set_proxy_port(user_input='@'):
            while not user_input.strip().isdigit() or not 0 <= int(user_input.strip()) <= 65535:
                user_input = input('Http proxy\'s port (eg: 8080): ')
            self.network['port'] = user_input

        def set_sortby(user_input='@'):
            while user_input not in ['speed', 'ping', 'score', 'up time', 'uptime']:
                user_input = input('Sort servers by (speed | ping | score | up time): ')
            self.filter['sort_by'] = 'up time' if user_input == 'uptime' else user_input

        def set_country_filter(user_input='@'):
            while not re.match('^[a-z ]*$', user_input.lower().strip()):
                user_input = input('Country\'s name (eg: [all], jp, japan): ')
            else:
                self.filter['country'] = 'all' if not user_input else user_input.lower()

        def set_port_filter(user_input='abc'):
            while not user_input.strip().isdigit():
                user_input = input('VPN server\'s port (eg: 995): ')
                if not user_input or 'all' == user_input: break
            self.filter['port'] = user_input if user_input else 'all'

        def set_proto_filter(user_input='abc'):
            while not user_input.strip() in ["tcp", "udp"]:
                user_input = input('Protocol ([all]|tcp|udp): ')
                if not user_input or 'all' == user_input: break
            self.filter['proto'] = user_input if user_input else 'all'

        def set_min_score(user_input='abc'):
            while not user_input.strip().isdigit():
                user_input = input('Minimum score of servers (eg: 200000): ')
                if not user_input or 'all' == user_input: break
            self.filter['score'] = user_input if user_input else 'all'

        def allow_dns_fix(user_input='@'):
            while user_input.lower() not in ['y', 'n', 'yes', 'no']:
                user_input = input('Fix DNS:')
            else:
                self.network['fix_dns'] = 'no' if user_input in 'no' else 'yes'

        def set_dns(user_input='@'):
            print('Default DNS are 8.8.8.8, 84.200.69.80, 208.67.222.222')
            while not re.match('[a-zA-Z0-9., ]*$', user_input.strip()):
                user_input = input('DNS server(s) with "," separated or Enter to use default: ')
            if user_input:
                self.network['dns'] = user_input.replace(' ', '').split(',')
            else:
                self.network['dns'] = '8.8.8.8, 84.200.69.80, 208.67.222.222'

        def set_mode(user_input='@'):
            while user_input not in ('main', 'fav', 'favorite'):
                user_input=input('mode ([main]|favorite): ')
                if not user_input:
                    user_input = 'main'

            self.network['mode'] = 'main' if user_input == 'main' else 'favorite'

        def allow_log(user_input='@'):
            while user_input.lower() not in ['y', 'n', 'yes', 'no']:
                user_input = input('Show openvpn log: ')
            else:
                self.show_log['verbose'] = 'no' if user_input in 'no' else 'yes'

        def set_mirror():
            while True:
                print(ctext('\n Current VPNGate\'s mirrors:', 'B'))
                for ind, url in enumerate(mirrors):
                    print(' ', ind, url)

                print('\nType ' + ctext("add %s", 'B') + ' or ' + ctext("del %d", 'B') +
                      ' to add or delete mirror \n'
                      '  where %s is a mirror\'s url and %d is index number of a mirror'
                      '\n  Or just Enter to leave it intact')

                while user_input.lower()[0:3] not in ("add", "del", ""):
                    user_input = input("\033[1mYour command: \033[0m")
                else:
                    if user_input.lower()[0:3] == "add":
                        url = user_input.lower()[3:].strip()
                        mirrors.append(url)
                    elif user_input.lower()[0:3] == "del":
                        number = user_input.lower()[3:].strip()
                        if number.isdigit() and int(number) < len(mirrors):
                            num = int(number)
                            mirrors.pop(num)
                        else:
                            print('  Index number is not exist!')
                    else:
                        self.mirrors['url'] = ', '.join(mirrors)
                        break

        def disable_ipv6(user_input='@'):
            while user_input.lower() not in ['y', 'n', 'yes', 'no']:
                user_input = input('Disable IPv6 during vpn?[yes|no]: ')
            else:
                self.network['disable_ipv6'] = 'no' if user_input in 'no' else 'yes'

        def auto_activate(user_input='@'):
            while user_input.lower() not in ['y', 'n', 'yes', 'no']:
                user_input = input('Allow automation?[yes|no]: ')
            else:
                self.automation['activate'] = 'no' if user_input in 'no' else 'yes'

        def auto_set_fetch_interval(user_input='@'):
            while True:
                try:
                    user_input = float(input('How long should server list be refresh? (>= 0.5 hour): '))
                except:
                    pass
                else:
                    self.automation['fetch_interval'] = str(user_input)
                    break

        flist = [allow_proxy,
                 set_proxy_addr, set_proxy_port,
                 allow_dns_fix,
                 set_dns,
                 set_mirror,
                 disable_ipv6,
                 set_mode,

                 set_sortby, set_min_score,
                 set_country_filter,
                 set_proto_filter, set_port_filter,

                 allow_log,

                 auto_activate,
                 auto_set_fetch_interval,
                 ]

        func = dict(zip((str(x) for x in range(1, len(flist)+1)), flist))
        not_need_refresh_func = [str(x) for x in (4, 5, 7, 8, 14, 15, 16)]

        while 1:
            vals = list(self.network.values())

            # network
            use_proxy, proxy, port, ip = vals[:4]
            fix_dns, dns = vals[6:8]
            ipv6, mode = vals[-2:]
            mirrors = self.mirrors['url']
            mirrors = mirrors.split(', ')

            # filter
            s_country, s_port, s_score = list(self.filter.values())[:3]
            proto, sort_by = list(self.filter.values())[3:]
            verbose = self.show_log['verbose']

            # automation
            fetch_interval = self.automation["fetch_interval"]
            activate = self.automation["activate"]

            print(ctext('\n ___Settings___', 'B'))
            print(ctext('\n Networking:', 'B'))
            print(ctext('    1. Use proxy:', 'yB'), use_proxy)
            print(ctext('    2. Proxy address:', 'yB'), proxy, ctext('\t3. port: ', 'yB'), port)
            print(ctext('    4. Fix dns leaking:', 'yB'), fix_dns)
            print(ctext('    5. DNS list: ', 'yB'), dns)
            print(ctext('    6. VPN gate\'s mirrors:', 'yB'), '%s ...' % mirrors[1])
            print(ctext('    7. Disable IP_v6:', 'yB'), '%s' % ipv6)
            print(ctext('    8. Mode:', 'yB'), '%s' % mode)


            print(ctext('\n Filter VPN server:', 'B'))
            print(ctext('    9. Sort by:', 'yB'), sort_by, ctext('    10. Minimum score:', 'yB'), s_score)
            print(ctext('    11. Country:', 'yB'), s_country)
            print(ctext('    12. Protocol:', 'yB'), proto, ctext('    13. VPN server\'s port: ', 'yB'), s_port)

            print(ctext('    14. Show openvpn log:', 'B'), verbose)

            print(ctext('\n Automation:', 'B'))
            print(ctext('    15. Activate:', 'yB'), activate)
            print(ctext('    16. Fetch interval:', 'yB'), fetch_interval)

            user_input = input('\nCommand or just Enter to continue: ')
            if user_input == '':
                self.write()
                return
            elif user_input not in func.keys():
                print("Invalid input!")
            else:
                func[user_input]()
                if user_input not in not_need_refresh_func:
                    return True


class FavoriteSevers(object):
    """Hold the list of favorite ovpn file"""
    def __init__(self, checker=None):
        self.path = sys.argv[1] + '/.config/vpngate-with-proxy'
        self.my_list = []
        self.load()

    @property
    def ip(self):
        return [x['ip'] for x in self.my_list]

    @property
    def dict(self):
        return {x.name: x for x in self}

    def add(self, server:Server=None, item:dict=None):
        if server:
            # add from vpngate.net
            for s in self.my_list:
                if s['ip'] == server.ip and s['port'] == server.port:
                    return False

            item = {'name': server.name,
                    'ip': server.ip,
                    'port': server.port,
                    'proto': server.proto,
                    'country': server.country_short,
                    'description': 'Saved from vpngate.net',
                    'path': f'favorites/{server.name}.ovpn'
                    }

            server.write_file(filename=f'favorites/{server.name}.ovpn').close()

        # else add from local
        self.my_list.append(item)
        with open('favorites/database.json', 'w+') as fo:
            json.dump(self.my_list, fo, indent=4)

        return True

    def remove(self, idx:list):
        try:
            remove_ls = [self.my_list[i] for i in idx]
            for toberemoved in remove_ls:
                self.my_list.remove(toberemoved)
                shutil.move(toberemoved['path'], toberemoved['path']+'.old')
        except (IndexError, FileNotFoundError) as e:
            return False

        with open('favorites/database.json', 'w+') as fo:
            json.dump(self.my_list, fo, indent=4)

        return True

    def load(self):
        """Load available saved data and return the number of server"""
        if not os.path.exists(self.path + '/favorites/database.json'):
            return 0

        with open('favorites/database.json') as fi:
            self.my_list = json.load(fi)
            return len(self.my_list)

    def add_local(self):
        ovpn = [x for x in os.listdir("favorites") if x[-4:]=='ovpn']
        for name in self.dict:
            if name+'.ovpn' in ovpn:
                ovpn.remove(name+'.ovpn')

        if not ovpn:
            print('No new ovpn file found!')
            return

        ovpn.sort()
        print('New ovpn file found:')
        for i in ovpn:
            print(' -> ', i)

        print()
        for name in ovpn:
            proto = ip = port = None
            with open(f'favorites/{name}') as candidate:
                try:
                    # validate basic info
                    for line in candidate:
                        if 'proto' == line[:5]:
                            proto = line.strip().split()[1]
                        elif 'remote' in line[:6]:
                            ip, port = line.strip().split()[1:]
                except:
                    if not all([proto, ip, port]):
                        print(f'Either proto|ip|port is missing: {name}')
                else:
                    # start adding
                    ui = input(f'Add "{name}" [country desription]?: ')
                    if ui.lower() in ['no','n']:
                        continue

                    country = '  '
                    descrip = 'Added from local'

                    ui = ui.split(' ', 1)
                    if len(ui) == 2:
                        country = ui[0][:2].upper()
                        descrip = ui[1]
                    elif len(ui) == 1 and ui[0]:
                        if len(ui[0]) == 2:
                            country = ui[0]
                        else:
                            descrip = ui[0]

                    item = {'name': name.strip('.ovpn'),
                            'ip': ip,
                            'port': port,
                            'proto': proto,
                            'country': country,
                            'description': descrip,
                            'path': f'favorites/{name}'
                            }

                    self.add(item=item)

    def __getattribute__(self, name):
        if name not in ['path', 'my_list', 'load', 'add_local']:
            self.load()
        return object.__getattribute__(self, name)

    def __len__(self):
        return len(self.my_list)

    def __getitem__(self, item):
        return Server(self.my_list[item], mode='favorite')

    def __str__(self):
        spaces = [6, 15, 8, 6, 16, 6]
        txt = ["Index       Name       Country  Proto        IP          Port      Description"]

        for ind, item in enumerate(self.my_list):
            line = [ind, item['name'], item['country'], item['proto'], item['ip'], item['port']]
            line = [str(x).center(spaces[i]) for i,x in enumerate(line)]
            line = ' '.join(line) + ' '*2 + item['description'][0:22]
            txt.append(line)

        return '\n'.join(txt)


def ctext(text, color):
    """ Add color to printed text
    :type text: str
    :type color: str
    """
    fcolor = {'p': '\033[95m',  # purple
              'b': '\033[94m',  # blue
              'g': '\033[92m',  # green
              'y': '\033[93m',  # yellow
              'r': '\033[91m',  # red

              'B': '\033[1m',  # BOLD
              'U': '\033[4m',  # UNDERLINE
              }

    ENDC = '\033[0m'

    tformat = ''.join([fcolor[fm] for fm in color])

    return tformat + text + ENDC


if __name__ == '__main__':
    fs = FavoriteSevers()
    fs.load()
    fs.add_local()