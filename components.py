from django.template.loader import render_to_string


SUCCESS = 'success'
PRIMARY = 'primary'
WARNING = 'warning'
DANGER = 'danger'


class Image(dict):
    def __init__(self, src, width=None, height=None, round=False):
        if width is None and height is None:
            width = 200
            height = 200
        self['type'] = 'image'
        self['src'] = src
        self['width'] = width
        self['height'] = height
        self['round'] = False


class Link(dict):
    def __init__(self, url, target='_blank', icon=None):
        self['type'] = 'link'
        self['url'] = url
        self['target'] = target
        self['icon'] = icon


class QrCode(dict):
    def __init__(self, text):
        self['type'] = 'qrcode'
        self['text'] = text


class Progress(dict):
    def __init__(self, value, style=None):
        self['type'] = 'progress'
        self['value'] = int(value or 0)
        self['style'] = style


class Status(dict):
    def __init__(self, style, label):
        self['type'] = 'status'
        self['style'] = style
        self['label'] = str(label)


class Badge(dict):
    def __init__(self, color, label):
        self['type'] = 'badge'
        self['color'] = color
        self['label'] = str(label)


class Indicators(dict):
    def __init__(self, title):
        self['type'] = 'indicators'
        self['title'] = title
        self['items'] = []
        self['actions'] = []

    def append(self, name, value):
        self['items'].append(dict(name=str(name), value=value))

    def action(self, label, url, modal=False):
        self['actions'].append(dict(label=str(label), url=url, modal=modal))


class Boxes(dict):
    def __init__(self, title):
        self['type'] = 'boxes'
        self['title'] = str(title)
        self['items'] = []

    def append(self, icon, label, url, style=None):
        self['items'].append(dict(icon=icon, label=str(label), url=url, style=style))

class Info(dict):
    def __init__(self, title, message):
        self['type'] = 'info'
        self['title'] = title
        self['message'] = message
        self['actions'] = []

    def action(self, label, url, modal=False, icon=None):
        self['actions'].append(dict(label=str(label), url=url, modal=modal, icon=icon))


class Warning(dict):
    def __init__(self, title, message):
        self['type'] = 'warning'
        self['title'] = title
        self['message'] = message
        self['actions'] = []

    def action(self, label, url, modal=False, icon=None):
        self['actions'].append(dict(label=str(label), url=url, modal=modal, icon=icon))


class Table(dict):
    def __init__(self, title, subset=None, pagination=None):
        self['type'] = 'table'
        self['title'] = title
        self['actions'] = []
        self['subsets'] = []
        self['subset'] = subset
        self['filters'] = []
        self['flags'] = []
        self['rows'] = []
        self['pagination'] = {}

    def add_subset(self, name, label, count):
        self['subsets'].append(dict(name=name, label=label, count=count))

    def add_action(self, name, label, icon=None, batch=True):
        self['actions'].append(dict(name=name, label=label, icon=icon, batch=batch))

    def add_flag(self, name, label, checked=False):
        self['flags'].append(dict(name=name, label=label, checked=checked))

    def add_filter(self, ftype, name, label, value, choices=None):
        self['filters'].append(dict(type=ftype, name=name, label=label, value=value, choices=choices))

    def pagination(self, size, page, total, sizes):
        self['pagination'].update(size=size, page=page, total=total, sizes=sizes)

    def add_row(self, row):
        self['rows'].append(row)

    def row(self, value=None, checkable=False, deleted=False):
        self['rows'].append([dict(name='#', value=value, checkable=checkable, deleted=deleted)])

    def cell(self, name, value, style=None, url=None, actions=None):
        self['rows'][-1].append(dict(name=name, value=value, style=style, url=url, actions=actions))


class TemplateContent(dict):
    def __init__(self, name, context):
        self['type'] = 'html'
        self['content'] = render_to_string(name, context)

class Banner(dict):
    def __init__(self, src):
        self['type'] = 'banner'
        self['src'] = src


class Map(dict):
    def __init__(self, latitude, longitude, width='100%', height=400):
        self['type'] = 'map'
        self['latitude'] = str(latitude)
        self['longitude'] = str(longitude)
        self['width'] = width
        self['height'] = height


class Steps(dict):
    def __init__(self, icon=None):
        self['type'] = 'steps'
        self['icon'] = icon
        self['steps'] = []

    def append(self, name, done):
        number = len(self['steps']) + 1
        self['steps'].append(dict(number=number, name=name, done=bool(done)))


class WebConf(dict):
    def __init__(self, caller, receiver):
        self['type'] = 'webconf'
        self['caller'] = caller
        self['receiver'] = receiver
