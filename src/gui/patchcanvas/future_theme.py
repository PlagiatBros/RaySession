#!/usr/bin/python3

import sys

from PyQt5.QtGui import QColor, QPen, QFont, QBrush
from PyQt5.QtCore import Qt

def print_error(string: str):
    sys.stderr.write("patchcanvas.theme::%s\n" % string)

def _to_qcolor(color):
    ''' convert a color given with a string, a list or a tuple (of ints)
    to a QColor.
    returns None if color has a incorrect value.'''
    if isinstance(color, str):
        qcolor = QColor(color)
        
        if (qcolor.getRgb() == (0, 0, 0, 255)
                and color.lower() not in ('black', "#000000", '#ff000000')):
            return None
        return qcolor
    
    if isinstance(color, (tuple, list)):
        if not 3 <= len(color) <= 4:
            return None

        for col in color:
            if not isinstance(col, int):
                return None
            
            if not 0 <= col <= 255:
                return None

        return QColor(*color)
    
    return None


class StyleAttributer:
    def __init__(self, path, parent=None):
        self.subs = []
        self._border_color = None
        self._border_width = None
        self._border_style = None
        self._background_color = None
        self._background2_color = None
        self._text_color = None
        self._font_name = None
        self._font_size = None
        self._font_width = None
        self._path = path
        self._parent = parent
    
    def set_attribute(self, attribute: str, value):
        err = False
        
        if attribute == 'border-color':
            self._border_color = _to_qcolor(value)
            if self._border_color is None:
                err = True
                
        elif attribute == 'border-width':
            if isinstance(value, (int, float)):
                self._border_width = float(value)
            else:
                err = True
                
        elif attribute == 'border-style':
            if isinstance(value, str):
                value = value.lower()
                if value == 'solid':
                    self._border_style = Qt.SolidLine
                elif value == 'nopen':
                    self._border_style = Qt.NoPen
                elif value == 'dash':
                    self._border_style = Qt.DashLine
                elif value == 'dashdot':
                    self._border_style = Qt.DashDotLine
                elif value == 'dashdotdot':
                    self._border_style = Qt.DashDotDotLine
                else:
                    err = True
            else:
                err = True

        elif attribute == 'background':
            self._background_color = _to_qcolor(value)
            if self._background_color is None:
                err = True
                
        elif attribute == 'background2':
            self._background2_color = _to_qcolor(value)
            if self._background2_color is None:
                err = True
                
        elif attribute == 'text-color':
            self._text_color = _to_qcolor(value)
            if self._text_color is None:
                err = True
                
        elif attribute == 'font-name':
            if isinstance(value, str):
                self._font_name = value
            else:
                err = True
                
        elif attribute == 'font-size':
            if isinstance(value, int):
                self._font_size = value
            else:
                err = True
                
        elif attribute == 'font-width':
            if isinstance(value, int):
                value = min(value, 99)
                value = max(value, 0)
                self._font_width = value
            elif isinstance(value, str):
                value = value.lower()
                if value == 'normal':
                    self._font_state = QFont.Normal
                elif value == 'bold':
                    self._font_state = QFont.Bold
                else:
                    err = True
            else:
                err = True
        else:
            print_error("%s:unknown key: %s" % (self._path, attribute))

        if err:
            print_error("%s:invalid value for %s: %s"
                        % (self._path, attribute, str(value)))
    
    def set_style_dict(self, context: str, style_dict: dict):
        if context:
            begin, point, end = context.partition('.')
            
            if begin not in self.subs:
                print_error("invalid ignored key: %s" % begin)
                return
            self.__getattribute__(begin).set_style_dict(end, style_dict)
            return
        
        for key, value in style_dict.items():
            self.set_attribute(key, value)
    
    def get_value_of(self, attribute, orig_path=''):
        if attribute not in self.__dir__():
            print_error("get_value_of, invalide attribute: %s" % attribute)
            return None
        
        if not orig_path:
            orig_path = self._path

        if (orig_path.endswith('.selected')
                and 'selected' in self.subs
                and self._path + '.selected' != orig_path):
            return self.selected.get_value_of(attribute, self._path)

        if self.__getattribute__(attribute) is None:
            if self._parent is None:
                print_error("get_value_of: %s None value and no parent"
                            % self._path)
                return None
            return self._parent.get_value_of(attribute, orig_path)

        return self.__getattribute__(attribute)
    
    def fill_pen(self):
        return QPen(QBrush(self.get_value_of('_border_color')),
                    self.get_value_of('_border_width'),
                    self.get_value_of('_border_style'))
    
    def background_color(self):
        return self.get_value_of('_background_color')
    
    def background2_color(self):
        return self.get_value_of('_background2_color')
    
    def text_color(self):
        return self.get_value_of('_text_color')
    
    def font(self):
        rfont = QFont()
        rfont.setFamily(self.get_value_of('_font_name'))
        rfont.setPixelSize(self.get_value_of('_font_size'))
        rfont.setWeight(self.get_value_of('_font_width'))
        return rfont


class UnselectedStyleAttributer(StyleAttributer):
    def __init__(self, path, parent=None):
        StyleAttributer.__init__(self, path, parent=parent)
        self.selected = StyleAttributer(path + '.selected', self)
        self.subs.append('selected')


class BoxStyleAttributer(UnselectedStyleAttributer):
    def __init__(self, path, parent):
        UnselectedStyleAttributer.__init__(self, path, parent)
        self.hardware = UnselectedStyleAttributer(path + '.hardware', self)
        self.client = UnselectedStyleAttributer(path + '.client', self)
        self.monitor = UnselectedStyleAttributer(path + '.monitor', self)
        self.subs += ['hardware', 'client', 'monitor']


class PortStyleAttributer(UnselectedStyleAttributer):
    def __init__(self, path, parent):
        UnselectedStyleAttributer.__init__(self, path, parent)
        self.audio = UnselectedStyleAttributer(path + '.audio', self)
        self.midi = UnselectedStyleAttributer(path + '.midi', self)
        self.cv = UnselectedStyleAttributer(path + '.cv', self)
        self.subs += ['audio', 'midi', 'cv']


class LineStyleAttributer(UnselectedStyleAttributer):
    def __init__(self, path, parent):
        UnselectedStyleAttributer.__init__(self, path, parent)
        self.audio = UnselectedStyleAttributer(path + '.audio', self)
        self.midi = UnselectedStyleAttributer(path + '.midi', self)
        self.subs += ['audio', 'midi']


class BodyStyleAttributer:
    def __init__(self, path):
        self._path = path
        self._background_color = QColor('black')
        self._port_height = 16
        self._port_spacing = 2
        self._port_type_spacing = 2
        self._box_spacing = 4
        self._box_spacing_horizontal = 24
        self._magnet = 12
        self._hardware_rack_width = 5
        
    def set_attribute(self, attribute: str, value):
        err = False

        if attribute == 'background':
            self._background_color = _to_qcolor(value)
            if self._background_color is None:
                err = True
                
        elif attribute == 'port-height':
            if isinstance(value, int):
                self._port_height = value
            else:
                err = True
        
        elif attribute == 'port-spacing':
            if isinstance(value, int):
                self._port_spacing = value
            else:
                err = True
        
        elif attribute == 'port-type-spacing':
            if isinstance(value, int):
                self._port_type_spacing = value
            else:
                err = True
        
        elif attribute == 'box-spacing':
            if isinstance(value, int):
                self._box_spacing = value
            else:
                err = True
        
        
        
        elif attribute == 'text-color':
            self._text_color = _to_qcolor(value)
            if self._text_color is None:
                err = True
                
        elif attribute == 'font-name':
            if isinstance(value, str):
                self._font_name = value
            else:
                err = True
                
        elif attribute == 'font-size':
            if isinstance(value, int):
                self._font_size = value
            else:
                err = True
                
        elif attribute == 'font-width':
            if isinstance(value, int):
                value = min(value, 99)
                value = max(value, 0)
                self._font_width = value
            elif isinstance(value, str):
                value = value.lower()
                if value == 'normal':
                    self._font_state = QFont.Normal
                elif value == 'bold':
                    self._font_state = QFont.Bold
                else:
                    err = True
            else:
                err = True
        else:
            print_error("%s:unknown key: %s" % (self._path, attribute))

        if err:
            print_error("%s:invalid value for %s: %s"
                        % (self._path, attribute, str(value)))
        

class Theme(StyleAttributer):
    def __init__(self):
        StyleAttributer.__init__(self, '')

        # fallbacks values for all (ugly style, but better than nothing)
        self._border_color = QColor('white')
        self._border_width = 1
        self._border_style = Qt.SolidLine
        self._background_color = QColor('black')
        self._background2_color = QColor('black')
        self._text_color = QColor('white')
        self._font_name = "Deja Vu Sans"
        self._font_size = 11
        self._font_width = QFont.Normal # QFont.Normal is 50

        self.background_color = QColor('black')
        self.port_height = 16
        self.port_spacing = 2
        self.port_type_spacing = 2
        self.box_spacing = 4
        self.box_spacing_horizontal = 24
        self.magnet = 12
        self.hardware_rack_width = 5

        self.box = BoxStyleAttributer('.box', self)
        self.portgroup = PortStyleAttributer('.portgroup', self)
        self.port = PortStyleAttributer('.port', self)
        self.line = LineStyleAttributer('.line', self)
        self.subs += ['box', 'portgroup', 'port', 'line']
        
    def read_theme(self, theme_dict: dict):
        if not isinstance(theme_dict, dict):
            print_error("invalid dict read error")
            return
        
        for key, value in theme_dict.items():
            begin, point, end = key.partition('.')
            
            if not isinstance(value, dict):
                print_error("'%s' must contains a dictionnary, ignored" % key)
                continue
            
            if key == 'body':
                for body_key, body_value in value.items():
                    if body_key in (
                            'port-height', 'port-spacing', 'port-type-spacing',
                            'box-spacing', 'box-spacing-horizontal', 'magnet',
                            'hardware-rack-width'):
                        if not isinstance(body_value, int):
                            continue
                        self.__setattr__(body_key.replace('-', '_'), body_value)
                    elif body_key == 'background':
                        self.background_color = _to_qcolor(body_value)
                        if self.background_color is None:
                            self.background_color = QColor('black')
                continue
            
            if begin not in self.subs:
                print_error("invalid ignored key: %s" % key)
                continue

            sub_attributer = self.__getattribute__(begin)
            sub_attributer.set_style_dict(end, value)


# theme = Theme()
default_theme = {
    # 'body':
    #     {'port-height': 26,
    #      'port-type-spacing': 14,
    #      'hardware-rack-width': 18},
    'box': 
        {'background': (20, 20, 20),
         'background2': (26, 24, 21),
         'border-color': (76, 77, 78),
         'text-color': (210, 210, 210),
         'font-size': 11,
         'font-width': 75
         },
    'box.selected':
        {'border-color': (206, 207, 208),
         'border-style': 'dash'
        },
    'box.client':
        {'font-name': 'Ubuntu'},
    'port':
        {'text-color': (200, 200, 200),
         'font-size': 11,
         'font-width': 50,
        },
    'port.audio':
        {'border-color': (100, 81, 0),
         'background': (40, 40, 48)
        },
    'port.audio.selected':
        {'background': (198, 161, 80),
         'text-color': (40, 40, 48)
        },
    'port.midi':
        {'border-color': (43, 23, 9),
         'background': (77, 42, 16),
         'text-color': (255, 255, 150)
        },
    'port.midi.selected':
        {'background': (160, 86, 33)
        },
    'port.cv':
        {'border-color': (100, 81, 0),
         'background': (20, 20, 25)
        },
    'port.cv.selected':
        {'background': (198, 161, 80)
        },
    'portgroup.audio':
        {'border-color': (100, 81, 0),
         'background': (25, 25, 30)
        },
    'portgroup.audio.selected':
        {'background': (209, 170, 86),
         'text-color': (25, 25, 30)
        },
    'line':
        {'border-width': 1.75
        },
    'line.audio':
        {'border-color': (60, 60, 72)
        },
    'line.audio.selected':
        {'border-color': (118, 118, 141)
        },
    'line.midi':
        {'border-color': (77, 42, 16)
        },
    'line.midi.selected':
        {'border-color': (160, 86, 33)
        }
    }

if __name__ == '__main__':
    theme = Theme()    
    theme.read_theme(default_theme)
    # print(theme.box.client.selected.get_value_of('_font_name'))
    # print(theme.port.audio.get_value_of('_border_width'))
    print(theme.port.audio.font())
    # print(theme.port.audio.background_color().blue())
    
# style_keys:
# border
# border_width
# background
# background_2
# font-name
# font-size
# font-state


# box
# box.selected
# box.hardware
# box.hardware.selected
# box.client
# box.client.selected
# box.monitor
# box.monitor.selected
# portgroup
# portgroup.selected
# portgroup.audio
# portgroup.audio.selected
# portgroup.midi
# portgroup.midi.selected
# portgroup.cv
# portgroup.cv.selected
# port
# port.selected
# port.audio
# port.audio.selected
# port.midi
# port.midi.selected
# port.cv
# port.cv.selected
# connection
# connection.selected
# connection.audio
# connection.audio.selected
# connection.midi
# connection.midi.selected



#shadow
#portgroup non défini devient valeurs de port
#line.glow
# line ready_to_disc
# gérer le dégradé de port/portgroup/line
# aliases de couleurs