# SPDX-FileCopyrightText: 2018-present Tobias Kunze
# SPDX-License-Identifier: AGPL-3.0-only WITH LicenseRef-Pretalx-AGPL-3.0-Terms

from django.dispatch import receiver

from pretalx.common.signals import register_data_exporters


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_ical")
def register_ical_exporter(sender, **kwargs):
    from pretalx.schedule.interfaces.exporters import (  # noqa: PLC0415 -- receiver
        ICalExporter,
    )

    return ICalExporter


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_faved_ical")
def register_faved_ical_exporter(sender, **kwargs):
    from pretalx.schedule.interfaces.exporters import (  # noqa: PLC0415 -- receiver
        FavedICalExporter,
    )

    return FavedICalExporter


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_xml")
def register_xml_exporter(sender, **kwargs):
    from pretalx.schedule.interfaces.exporters import (  # noqa: PLC0415 -- receiver
        FrabXmlExporter,
    )

    return FrabXmlExporter


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_xcal")
def register_xcal_exporter(sender, **kwargs):
    from pretalx.schedule.interfaces.exporters import (  # noqa: PLC0415 -- receiver
        FrabXCalExporter,
    )

    return FrabXCalExporter


@receiver(register_data_exporters, dispatch_uid="exporter_builtin_json")
def register_json_exporter(sender, **kwargs):
    from pretalx.schedule.interfaces.exporters import (  # noqa: PLC0415 -- receiver
        FrabJsonExporter,
    )

    return FrabJsonExporter
