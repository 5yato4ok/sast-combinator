import os


def vars_substitute():
    os.environ['DOLLAR'] = '$'
    os.environ['CUSTOMIZATION'] = args.customization
    os.environ['DATA_HOSTS_STR'] = DATA_HOSTS_STR
    os.environ['PORTAL_HOST'] = args.portal_host
    os.environ['PORTAL_BUCKET'] = args.portal_bucket

    with open(os.path.join(NGINX_DEPLOYMENT_DIR, 'nginx.conf.template'), 'r') as template_file:
        template = template_file.read()
    return template


os.makedirs(NGINX_LOCAL_DIR, exist_ok=True)
vars_substitute()
