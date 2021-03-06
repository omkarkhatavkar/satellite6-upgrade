"""A set of upgrade tasks for upgrading Satellite, Capsule and Client.

Many commands are affected by environment variables. Unless stated otherwise,
all environment variables are required.
"""
import os

from automation_tools import foreman_debug
from automation_tools.satellite6.log import LogAnalyzer
from upgrade.capsule import (
    satellite6_capsule_setup,
    satellite6_capsule_upgrade,
    satellite6_capsule_zstream_upgrade
)
from upgrade.client import (
    satellite6_client_setup,
    satellite6_client_upgrade
)
from upgrade.satellite import (
    satellite6_setup,
    satellite6_upgrade,
    satellite6_zstream_upgrade
)
from upgrade.helpers.logger import logger
from upgrade.helpers.tasks import (
    check_necessary_env_variables_for_upgrade,
    post_upgrade_test_tasks
)
from upgrade.helpers.tools import (
    create_setup_dict,
    get_sat_cap_version,
    get_setup_data
)
from distutils.version import LooseVersion
from fabric.api import env, execute


# =============================================================================
# Satellite, Capsule and Client Upgrade
# =============================================================================

logger = logger()


def setup_products_for_upgrade(product, os_version):
    """Sets up product(s) to perform upgrade on

    :param string product: The product name to setup before upgrade
    :param string os_version: The os version on which product is installed
        e.g: rhel6, rhel7
    """
    if check_necessary_env_variables_for_upgrade(product):
        sat_host = cap_hosts = clients6 = clients7 = None
        logger.info('Setting up Satellite ....')
        sat_host = satellite6_setup(os_version)
        if product == 'capsule' or product == 'n-1' or product == 'longrun':
            logger.info('Setting up Capsule ....')
            cap_hosts = satellite6_capsule_setup(
                sat_host, os_version, False if product == 'n-1' else True)
        if product == 'client' or product == 'longrun':
            logger.info('Setting up Clients ....')
            clients6, clients7, puppet_clients7 = satellite6_client_setup()
        setups_dict = {
            'sat_host': sat_host,
            'capsule_hosts': cap_hosts,
            'clients6': clients6,
            'clients7': clients7,
            'puppet_clients7': puppet_clients7
        }
        create_setup_dict(setups_dict)
        return sat_host, cap_hosts, clients6, clients7, puppet_clients7


def product_upgrade(product):
    """Task which upgrades the product.

    Product is satellite or capsule or client or longrun.
    If product is satellite then upgrade only satellite
    If product is capsule then upgrade satellite and capsule
    If product is client then upgrade satellite and client
    If product is longrun then upgrade satellite, capsule and client
    If product is n-1 then upgrades only satellite by keeping capsule at last
    z-stream released version

    :param string product: product name wanted to upgrade.

    Environment Variables necessary to proceed Upgrade:
    -----------------------------------------------------

    FROM_VERSION
        The satellite/capsule current version to upgrade to latest.
        e.g '6.2','6.1'
    TO_VERSION
        To which Satellite/Capsule version to upgrade.
        e.g '6.3','6.2'
    OS
        The OS Version on which the satellite is installed.
        e.g 'rhel7','rhel6'

    Environment variables populated from jenkins:
    ------------------------------------------------------

    RHN_USERNAME
        Red Hat Network username to register the system.
    RHN_PASSWORD
        Red Hat Network password to register the system.
    RHN_POOLID
        Optional. Red Hat Network pool ID. Determines what software will be
        available from RHN
    BASE_URL
        URL for the compose repository.
    CAPSULE_URL
        The url for capsule repo from latest satellite compose.
        If CDN, defaults to latest available capsule version
    TOOLS_URL_RHEL6
        The url for rhel6 tools repo from latest satellite compose
        If CDN, defaults to latest available tools version
    TOOLS_URL_RHEL7
        The url for rhel7 tools repo from latest satellite compose
        If CDN, defaults to latest available tools version

    Environment variables required to run upgrade on user's own setup:
    --------------------------------------------------------------------

    SATELLITE_HOSTNAME
        The Satellite hostname to run upgrade on
    CAPSULE_HOSTNAME
        The Satellite hostname to run upgrade on
    CLIENT6_HOSTS
        The RHEL6 clients hostnames to run upgrade on
    CLIENT7_HOSTS
        The RHEL7 clients hostnames to run upgrade on.
    CAPSULE_AK
        Activation Key name attached to the subscription of capsule
    CLIENT_AK
        Activation Key name attached to the subscription of client

    Environment variables required to run upgrade on RHEVM Setup and will be
    fetched from Jenkins:
    ----------------------------------------------------------------------

    RHEV_SAT_IMAGE
        The satellite Image from which satellite instance will be created
    RHEV_SAT_HOST
        The rhevm satellite hostname to run upgrade on
    RHEV_CAP_IMAGE
        The capsule Image from which capsule instance will be created
    RHEV_CAP_HOST
        The rhevm capsule hostname to run upgrade on
    DOCKER_VM
        The Docker VM IP/Hostname on rhevm to create and upgrade clients
    CLIENTS_COUNT
        The number of clients(docker containers) to generate to run upgrade
    RHEV_CAPSULE_AK
        The AK name used in capsule subscription
    RHEV_CLIENT_AK
        The AK name used in client subscription
    """
    if check_necessary_env_variables_for_upgrade(product):
        from_version = os.environ.get('FROM_VERSION')
        to_version = os.environ.get('TO_VERSION')
        logger.info('Performing UPGRADE FROM {0} TO {1}'.format(
            from_version, to_version))
        # Get the setup dict returned by setup_products_for_upgrade
        setup_dict = get_setup_data()
        sat_host = setup_dict['sat_host']
        env['satellite_host'] = sat_host
        try:
            with LogAnalyzer(sat_host):
                current = execute(
                    get_sat_cap_version, 'sat', host=sat_host)[sat_host]
                if from_version != to_version:
                    execute(satellite6_upgrade, host=sat_host)
                else:
                    execute(satellite6_zstream_upgrade, host=sat_host)
                upgraded = execute(
                    get_sat_cap_version, 'sat', host=sat_host)[sat_host]
                if LooseVersion(upgraded) > LooseVersion(current):
                    logger.highlight(
                        'The Satellite is upgraded from {0} to {1}'.format(
                            current, upgraded))
                else:
                    logger.highlight(
                        'The Satellite is NOT upgraded to next version. Now '
                        'its {}'.format(upgraded))
                # Generate foreman debug on satellite after upgrade
                execute(foreman_debug, 'satellite_{}'.format(sat_host),
                        host=sat_host)
                if product == 'capsule' or product == 'longrun':
                    cap_hosts = setup_dict['capsule_hosts']
                    for cap_host in cap_hosts:
                        try:
                            with LogAnalyzer(cap_host):
                                current = execute(
                                    get_sat_cap_version, 'cap', host=cap_host
                                    )[cap_host]
                                if from_version != to_version:
                                    execute(satellite6_capsule_upgrade,
                                            cap_host, sat_host, host=cap_host)
                                elif from_version == to_version:
                                    execute(satellite6_capsule_zstream_upgrade,
                                            cap_host, host=cap_host)
                                upgraded = execute(
                                    get_sat_cap_version, 'cap', host=cap_host
                                    )[cap_host]
                                if current:
                                    if LooseVersion(upgraded) > LooseVersion(
                                            current):
                                        logger.highlight(
                                            'The Capsule is upgraded from {0} '
                                            'to {1}.'.format(current, upgraded)
                                        )
                                    else:
                                        logger.highlight(
                                            'The Capsule is NOT upgraded to '
                                            'next version. Now its {}'.format(
                                                upgraded))
                                else:
                                    logger.highlight(
                                        'Unable to fetch previous version but '
                                        'after upgrade capsule is {}.'.format(
                                            upgraded))
                                # Generate foreman debug on capsule postupgrade
                                execute(
                                    foreman_debug,
                                    'capsule_{}'.format(cap_host),
                                    host=cap_host)
                        except Exception:
                            # Generate foreman debug on failed capsule upgrade
                            execute(
                                foreman_debug, 'capsule_{}'.format(cap_host),
                                host=cap_host)
                            raise
                if product == 'client' or product == 'longrun':
                    clients6 = setup_dict['clients6']
                    clients7 = setup_dict['clients7']
                    puppet_clients7 = setup_dict['puppet_clients7']
                    satellite6_client_upgrade('rhel6', clients6)
                    satellite6_client_upgrade('rhel7', clients7)
                    satellite6_client_upgrade(
                        'rhel7', puppet_clients7, puppet=True)
                if product == 'longrun':
                    # Execute tasks as post upgrade tier1 tests
                    # are dependent
                    post_upgrade_test_tasks(sat_host, cap_host)
        except Exception:
            # Generate foreman debug on failed satellite upgrade
            execute(foreman_debug, 'satellite_{}'.format(sat_host),
                    host=sat_host)
            raise
