# pdu

Manage APC PDUs

# Installation

```
git clone git@github.com:gregorg/pdu.git
cd pdu
poetry install
```

# Configuration

In the first run you must specify the location of your config file:
```
poetry run pdu --config ~/yoursysadminrepo/pdu.ini
```

# Usage

To fetch a PDU config and save it to config file previously setupped :
```
poetry run pdu --debug --save --pdu 10.0.0.2
```

To reboot a server which is charged by 2 outlets :
```
poetry run pdu --reboot server-42
```

To read config file and apply differences between current PDU's config (you will be warmed and have to confirm every changes) ::
```
poetry run pdu --read
```
