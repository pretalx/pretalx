.. SPDX-FileCopyrightText: 2025-present Tobias Kunze
.. SPDX-License-Identifier: CC-BY-SA-4.0

Licensing
=========

.. warning::

    This page tries to break down what the pretalx license does and does not allow. It is not legal advice. Only the `original text of the license <https://github.com/pretalx/pretalx/blob/main/LICENSE>`_ is legally binding.

How is pretalx licensed?
-------------------------

pretalx is available under the `GNU Affero General Public License 3 <https://www.gnu.org/licenses/agpl-3.0.en.html>`_ (AGPL) with additional terms (one permission and two restrictions).

Why did you choose this license model?
---------------------------------------

pretalx was born in the open source community and has been developed openly since 2017.
This has allowed event organisers from all communities and regions to use a self-hosted, privacy-friendly option to manage their conferences, with the ability to add plugins or modify the software itself if needed.

This is really important to us. Or rather, let me break the “proper project writing style“ voice for a moment: This is really important to me.
Developing pretalx has been – and still is – a lot of work. And while there have been external contributions, the vast majority of the development has been done by me (hi).
pretalx has grown very slowly, but steadily: It took eight years of working on it on the side before it started to become my primary source of income.

Changing the project license from Apache 2.0 to AGPL is about protecting the sustainability of the project, both for the community and for myself.
To put it even more plainly: The more pretalx becomes my primary income, the bigger looms the threat of somebody taking the result of years of my work, closing it up, and offering it as a service themselves, leaving me high and dry.

The AGPL is the best solution I found: It ensures that pretalx will remain open source, and that anybody building a service on top of it will have to contribute their improvements back to the community.
Plus, it is a proven model: I have cribbed the license terms from the `pretix <https://docs.pretix.eu/trust/licensing/faq/>`_ project, and I remain thankful to both their public and transparent work, and their kind advice and support.

Using pretalx without modifications
-----------------------------------

If you use pretalx without any modifications or plugins, you can use it for whatever you want, including redistribution, as long as you keep all copyright notices (including the “powered by pretalx” link) in place.

If you install **plugins**, you must follow the same terms as when using a **modified** version (see below).

Using pretalx with modifications
--------------------------------

You have the right to modify pretalx. However, you need to follow these rules:

- If you **run pretalx for your own events** (events run by you or your organisation), our additional permission allows you to do so **without needing to share your source code modifications** as long as you keep the “powered by pretalx” link intact.
- If you **run pretalx for others**, for example as part of a Software-as-a-Service offering or a managed hosting service, you **must** make the source code **including all your modifications and all installed plugins** available under the same license as pretalx to every visitor of your site. You need to do so in a prominent place such as a link in the footer. You also **must** keep the existing “powered by pretalx“ link intact. You **may not** add additional restrictions on the result as a whole. You **may** add additional permissions, but only on the parts you added. You **must** make clear which changes you made and you must not give the impression that your modified version is an official version of pretalx.
- If you **distribute** the modified version, for example as a source code or software package, you **must** license it under the AGPL license with the same additional terms. You **may not** add additional restrictions on the result as a whole. You **may** add additional permissions, but only on the parts you added. You **must** make clear which changes you made and you must not give the impression that your modified version is an official version of pretalx.

Plugins and the AGPL copyleft mechanism
---------------------------------------

The AGPL copyleft mechanism **extends to plugins**. pretalx plugins are tightly integrated with pretalx, so when running pretalx together with a plugin in the same environment they form a `combined work <https://www.gnu.org/licenses/gpl-faq.html#GPLPlugins>`_ and the copyleft mechanism of AGPL applies.

Proprietary and closed-source plugins
-------------------------------------

You can create a proprietary or closed-source plugin, but it may only ever be **used** in an environment that is covered by the additional permission from our license.
As soon as the plugin is installed in an installation that is not covered by our additional permission (e.g. when it is used in a SaaS environment), it **must** be released to the visitors of the site under the same license as pretalx (like any modified version of pretalx).

Plugin licensing
----------------

Technically, you can distribute a plugin under any free or proprietary license as long as it is distributed separately. However, once it is either **distributed together with pretalx or used in an environment not covered by our additional permission**, you **must** release it to all recipients of the distribution or all visitors of your site under the same license as pretalx (like any modified version of pretalx).

Note that when you license a plugin under pure AGPL, it will be incompatible with our additional permission. Therefore, if you want to use an AGPL-licensed plugin, you'll need to publish the source code of **all** your plugins under AGPL terms **even if you only use it for your own events**.
A plugin could add its `own additional permission <https://www.gnu.org/licenses/gpl-faq.html#GPLIncompatibleLibs>`_ to its license to allow combining it with pretalx for this use case.

To make things less complicated, if you want to distribute a plugin freely, we recommend you use a license that is `compatible with AGPL <https://www.gnu.org/licenses/license-list.en.html#GPLCompatibleLicenses>`_.
This includes most open source licenses such as AGPL, GPL, Apache, 3-clause BSD or MIT.
Our own open-source plugins are licensed under **Apache License 2.0**.

Contributions and licensing
---------------------------

Before accepting your contributions, we will ask you to sign a Contributor License Agreement (CLA) that gives us permission to use your contribution in all present and future distributions of pretalx.
We're not a fan of the bureaucracy involved either – sorry about that.
