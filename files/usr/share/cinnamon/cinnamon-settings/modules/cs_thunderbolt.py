#!/usr/bin/python3

from SettingsWidgets import SidePage
from xapp.GSettingsWidgets import *
import os

class BoltDevice:
    def __init__(self, proxy, trust_callback, forget_callback):
        self._proxy = proxy
        self._trust = trust_callback
        self._forget = forget_callback
        self.name = proxy.get_cached_property('Name').unpack()
        self.vendor = proxy.get_cached_property('Vendor').unpack()
        self.uid = proxy.get_cached_property('Uid').unpack()
        self.status = proxy.get_cached_property('Status').unpack()
        self.stored = proxy.get_cached_property('Stored').unpack()

        # Build the widgets for this bolt device
        self._init_widgets()
        
        # Use this signal to key into device status changes
        self._proxy.connect('g-properties-changed', self._on_prop_changes)

    def _init_widgets(self):
        self.status_label = Gtk.Label.new()
        self._btn_auth = Gtk.Button.new_with_label(_("Authorize"))
        self._btn_auth.connect('clicked', self._on_btn_auth_click)
        self._btn_trust = Gtk.Button.new()
        self._btn_trust.connect('clicked', self._on_btn_trust_click)
        self.buttons = Gtk.ButtonBox.new(Gtk.Orientation.HORIZONTAL)
        self.buttons.pack_start(self._btn_auth, True, True, 0)
        self.buttons.pack_end(self._btn_trust, True, True, 0)
        self.buttons.set_layout(Gtk.ButtonBoxStyle.EXPAND)
        self._refresh()

    def _refresh(self):
        # Refresh widgets based on current state
        self._btn_auth.set_sensitive(False)
        text = self.status.title()
        if self.stored:
            text = text + ", " + _("Trusted")
            self._btn_trust.set_label(_("Forget"))
        else:
            self._btn_trust.set_label(_("Trust"))
            if self.status == 'connected':
                self._btn_auth.set_sensitive(True)
        self.status_label.set_label(text)

    def _on_btn_auth_click(self, button):
        self._proxy.Authorize('(s)', 'auto')
        button.set_sensitive(False)

    def _on_btn_trust_click(self, button):
        if self.stored:
            self._forget(self.uid)
        else:
            self._trust(self.uid)

    def _on_prop_changes(self, proxy, changed, invalidated):
        # Update current state as properties change
        changed = changed.unpack()
        if 'Stored' in changed:
            self.stored = changed['Stored']
        if 'Status' in changed:
            self.status = changed['Status']
        self._refresh()

def build_info_row(key, widget):
    row = SettingsWidget()
    labelKey = Gtk.Label.new(key)
    row.pack_start(labelKey, False, False, 0)
    row.pack_end(widget, False, False, 0)
    return row

class Module:
    name = "thunderbolt"
    category = "hardware"
    comment = _("Manage Thunderbolt™ devices")

    def __init__(self, content_box):
        keywords = _("thunderbolt")
        sidePage = SidePage("Thunderbolt™", "thunderbolt-symbolic", keywords, content_box,
                            module=self)
        self.sidePage = sidePage

    def _loadCheck(self):
        """Checks if whether Thunderbolt is present on the system bus."""
        return os.path.isdir('/sys/bus/thunderbolt')

    def on_module_selected(self):
        # Check if we've already been loaded
        if self.loaded:
            return

        print("Loading Thunderbolt module")

        # Get the Bolt Manager proxy
        try:
            self.manager_proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                'org.freedesktop.bolt',
                '/org/freedesktop/bolt',
                'org.freedesktop.bolt1.Manager',
                None
                )
        except GLib.Error:
            self.manager_proxy = None
            print('Cannot acquire org.freedesktop.bolt1.Manager proxy')
            return

        # Subscribe to signals to act on device adds/removals
        self.manager_proxy.connect('g-signal', self._on_manager_proxy_g_signal)

        # Define the settings page
        self.page = SettingsPage()
        self.page.set_spacing(24)
        self.sidePage.add_widget(self.page)

        # Create initial sections for each device
        self._bolt_sections = dict()

        # Initialize known bolt devices
        for obj_path in self.manager_proxy.ListDevices():
            self._build_section(obj_path)

    def _build_section(self, obj_path):
        # Check if we've already built this section
        if obj_path in self._bolt_sections:
            print('Already built section for', obj_path)
            return

        # Get the device proxy
        try:
            proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM,
                Gio.DBusProxyFlags.NONE,
                None,
                'org.freedesktop.bolt',
                obj_path,
                'org.freedesktop.bolt1.Device',
                None
                )
        except GLib.Error:
            print('Cannot acquire org.freedesktop.bolt1.Device proxy for path', obj_path)
            return

        # Don't build section for host
        if proxy.get_cached_property('Type').unpack() == 'host':
            print('Skipping host type')
            return

        # Init the device and the corresponding section
        bolt_dev = BoltDevice(proxy, self._trust_device, self._forget_device)
        section = self.page.add_section(bolt_dev.name)
        section.add_row(build_info_row('Vendor', Gtk.Label.new(bolt_dev.vendor)))
        section.add_row(build_info_row('UID', Gtk.Label.new(bolt_dev.uid)))
        section.add_row(build_info_row('Status', bolt_dev.status_label))
        widget = SettingsWidget()
        widget.pack_start(bolt_dev.buttons, True, True, 0)
        section.add_row(widget)
        section.show_all()

        # Add to bolt sections we're maintaining
        self._bolt_sections[obj_path] = (section, bolt_dev)

    def _trust_device(self, uid):
        print('Trusting', uid)
        self.manager_proxy.EnrollDevice('(sss)', uid, 'auto', '')

    def _forget_device(self, uid):
        print('Forgetting', uid)
        self.manager_proxy.ForgetDevice('(s)', uid)

    def _on_manager_proxy_g_signal(self, proxy, sender, signal, parameters):
        if signal == 'DeviceAdded':
            (obj_path,) = parameters.unpack()
            self._build_section(obj_path)
        elif signal == 'DeviceRemoved':
            (obj_path,) = parameters.unpack()
            if obj_path in self._bolt_sections:
                self._bolt_sections[obj_path][0].destroy()
                del self._bolt_sections[obj_path]
        

