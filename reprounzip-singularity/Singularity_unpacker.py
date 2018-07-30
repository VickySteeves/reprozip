import copy
import tarfile
import os
import sys
import yaml
import subprocess
import io
import string

SINGULARITY_DIR = "../.singularity.d"
APP_DIR = "../sample_app"
MOUNT_DIR = "/mnt/"
RUN_ENV_FILE = "90-environment.sh"
APP_BASE_FILE = "01-base.sh"
MAIN_APP_BASE_FILE = ".singularity.d/env/94-appsbase.sh"
RUNSCRIPT = "runscript"
IMAGE_TAR_FILE = "new.tar.gz"
SOURCE_CONFIG = "METADATA/config.yml"
OVERLAY_IMAGE = "repro_overlay.img"

safe_shell_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                       "abcdefghijklmnopqrstuvwxyz"
                       "0123456789"
                       "-+=/:.,%_")

def sanitize_appname(name):
    name = name.strip()
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    valid_name = ''.join(c for c in name if c in valid_chars)
    valid_name = valid_name.replace(' ','_')
    return valid_name

def shell_escape(s):
    """Given bl"a, returns "bl\\"a".
    """
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    if not s or any(c not in safe_shell_chars for c in s):
        return '"%s"' % (s.replace('\\', '\\\\')
                          .replace('"', '\\"')
                          .replace('`', '\\`')
                          .replace('$', '\\$'))
    else:
        return s


def write_env_file(tar, env, env_file, app_name=None):
    cmd = ''
    for key,value in env.items():
            cmd += shell_escape(key)+ "='" + shell_escape(value)+"'\n"
   
    env_file = "scif/apps/"+app_name+"/scif/env/" + env_file
    cmd = cmd.encode('utf-8')
    t = tarfile.TarInfo(env_file)
    t.size = len(cmd)
    t.mode = 0o755
    tar.addfile(t, io.BytesIO(cmd))
        
def make_app_runscript(tar, cmd, app_name=None):
    file = "scif/apps/"+app_name+"/scif/"+ RUNSCRIPT
    cmd = cmd.encode("utf-8")
    t = tarfile.TarInfo(file)
    t.mode=0o755
    t.size = len(cmd)
    tar.addfile(t, io.BytesIO(cmd))

   
def make_runscript(tar, cmd, workingdir):
    run_cmd = "run()\n"
    run_cmd += "{"+ cmd + "\n}\n\n"
    upload_download_cmd = "upload()\n{\n"
    upload_download_cmd += "\tcp " + MOUNT_DIR + "\"$1\" " + workingdir + "\n}\n\n"
    upload_download_cmd += "download()\n{\n"
    upload_download_cmd += "\tcp {0}/".format(workingdir) + "\"$1\" " + MOUNT_DIR + "\n}\n\n"
    upload_download_cmd += "if [ \"$#\" -gt 0 ]\nthen \n \tcase \"$1\" in \n\t\t\"upload\"|\"download\")\n\t\t\t\"$1\" \"$2\" \n\t\t;;\n\t\t*)\n\t\techo \"Invalid arguments!!\" >&2\n\t\texit 1\n\t\t;;\n\tesac\nelse\n\trun\nfi"
    file = ".singularity.d/"+ RUNSCRIPT
    run_cmd = run_cmd + upload_download_cmd
    run_cmd=run_cmd.encode("utf-8")
    t = tarfile.TarInfo(file)
    t.size = len(run_cmd)
    t.mode=0o755
    tar.addfile(t, io.BytesIO(run_cmd))
    
def get_main_app_base_script_content(app_name=None):
    cmd =  "SCIF_APPDATA_{0}=/scif/data/{1}\n".format(app_name,app_name)
    cmd += "SCIF_APPMETA_{0}=/scif/apps/{1}/scif\n".format(app_name,app_name)
    cmd += "SCIF_APPROOT_{0}=/scif/apps/{1}\n".format(app_name,app_name)
    cmd += "SCIF_APPBIN_{0}=/scif/apps/{1}/bin\n".format(app_name,app_name)
    cmd += "SCIF_APPLIB_{0}=/scif/apps/{1}/lib\n".format(app_name,app_name)
    cmd += "export SCIF_APPDATA_{0} SCIF_APPROOT_{1} SCIF_APPMETA_{2} SCIF_APPBIN_{3} SCIF_APPLIB_{4}\n".format(app_name,app_name,app_name,app_name,app_name)
    cmd += "SCIF_APPENV_{0}=/scif/apps/{1}/scif/env/90-environment.sh\n".format(app_name,app_name)
    cmd += "export SCIF_APPENV_{0}\n".format(app_name)
    cmd += "SCIF_APPLABELS_{0}=/scif/apps/{1}/scif/labels.json\n".format(app_name,app_name)
    cmd += "export SCIF_APPLABELS_{0}\n".format(app_name)
    cmd += "SCIF_APPRUN_{0}=/scif/apps/{1}/scif/runscript\n".format(app_name,app_name)
    cmd += "export SCIF_APPRUN_{0}\n".format(app_name)
    return cmd


def make_main_app_base_script(tar, main_app_base_cmd):
    main_app_base_cmd = main_app_base_cmd.encode('utf-8')
    t = tarfile.TarInfo(MAIN_APP_BASE_FILE)
    t.size = len(main_app_base_cmd)
    tar.addfile(t, io.BytesIO(main_app_base_cmd))


def make_app_specific_base_script(tar, file, app_name=None):
    cmd = "SCIF_APPNAME={}\n".format(app_name)
    cmd += "SCIF_APPROOT=\"/scif/apps/{}\"\n".format(app_name)
    cmd += "SCIF_APPMETA=\"/scif/apps/{}/scif\"\n".format(app_name)
    cmd += "SCIF_DATA=\"/scif/data\"\n"
    cmd += "SCIF_APPDATA=\"/scif/data/{}\"\n".format(app_name)
    cmd += "SCIF_APPINPUT=\"/scif/data/{}/input\"\n".format(app_name)
    cmd += "SCIF_APPOUTPUT=\"/scif/data/{}/output\"\n".format(app_name)
    cmd += "export SCIF_APPDATA SCIF_APPNAME SCIF_APPROOT SCIF_APPMETA SCIF_APPINPUT SCIF_APPOUTPUT SCIF_DATA\n"
    cmd = cmd.encode("utf-8")
    file = "scif/apps/" + app_name +"/scif/env/" + file
    t = tarfile.TarInfo(file)
    t.size = len(cmd)
    tar.addfile(t, io.BytesIO(cmd))

# Check if bin is present in the tar if not add bin and sh
def copy_busybox(tar):
  tar.add("../bin",arcname="bin")

def add_singularity_folder(tar):
    # check if the runs are multiple or single
    tar.add(SINGULARITY_DIR, arcname=".singularity.d")
    my_dict = yaml.load(open(SOURCE_CONFIG))
    runs = my_dict['runs']
    main_app_base_cmd = ''
    main_run_cmd = ''
    copy_busybox(tar)
    # Add scif folders - apps and data
    for folder in ["apps","data"]:
        new_info = tarfile.TarInfo("scif/"+folder)
        new_info.type = tarfile.DIRTYPE
        new_info.mode = 0o755
        tar.addfile(new_info)
    for run in runs:
        binary = run['binary']
        workingdir = run['workingdir']
        run_file = run['argv'][1]
        app_name = run['id']
        #sanitize the app_name
        app_name = sanitize_appname(app_name)
        # add the app
        tar.add(APP_DIR, arcname="scif/apps/" + app_name)
        # Make app specific runscript 
        cmd = "cd {0}\n{1} {2}\n".format(workingdir, binary, run_file)
        make_app_runscript(tar, cmd, app_name)
        # Make the environment file
        write_env_file(tar,run.get('environ'), RUN_ENV_FILE, app_name)
        # Add the app base script
        make_app_specific_base_script(tar, APP_BASE_FILE, app_name)
        # Get the main app base script content
        main_app_base_cmd += get_main_app_base_script_content(app_name)  
        # get consolidated app run commands for main runscript
        main_run_cmd += "\n\techo \"running app: "+ app_name + "\""
        main_run_cmd += "\n\tsource /scif/apps/"+ app_name + "/scif/env/" + RUN_ENV_FILE 
        main_run_cmd += "\n\tsource /scif/apps/"+ app_name + "/scif/" + RUNSCRIPT 
    if main_run_cmd:
         make_runscript(tar,main_run_cmd,runs[0]['workingdir'])
    if main_app_base_cmd:
        make_main_app_base_script(tar,main_app_base_cmd)

def create_overlay_image(OVERLAY_IMAGE):
    if not os.path.exists(OVERLAY_IMAGE):
        bashCommand = "singularity image.create {}".format(OVERLAY_IMAGE)
        process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
        output, error = process.communicate()
    
def setup(filename):
    # Open outer tar, the RPZ file
    rpz = tarfile.open(filename, 'r:*')
    # Open the inner tar in the original, without extracting it to disk
    data = rpz.extractfile('DATA.tar.gz')
    tar = tarfile.open('DATA.tar.gz', fileobj=data)
    # Open the new tar we're writing
    new = tarfile.open('new.tar.gz', 'w:gz')
    # For each member of the data tar
    for info in tar.getmembers():
        # Make a new TarInfo, removing the DATA/ prefix from the file name
        new_info = copy.copy(info)
        new_info.name = info.name[5:]
        if new_info.name:
            # Copy the file from the inner tar to the new tar
            if new_info.isreg():
                new.addfile(new_info, tar.extractfile(info.name))
            else:
                new.addfile(new_info)
    folders = ['proc','dev','sys','temp_home','mnt']
    for folder in folders:
        new_info = tarfile.TarInfo(folder)
        new_info.type = tarfile.DIRTYPE
        new_info.mode=0o755
        new.addfile(new_info)

    rpz.extract("METADATA/config.yml",path="")
    add_singularity_folder(new)
    create_overlay_image(OVERLAY_IMAGE)
    tar.close()
    data.close()
    rpz.close()
    new.close()

def run(IMAGE_TAR_FILE, app):
    home = os.environ['HOME']
    if app:
        print("running app:{}!".format(app))
        bashCommand = "singularity run  --overlay {0} --app {1} -C -H {2}:/temp_home {3}".format(OVERLAY_IMAGE,app,home,IMAGE_TAR_FILE)
        try:
            subprocess.check_call([bashCommand],shell=True)
        except subprocess.CalledProcessError:
            print("Error running '{0}'".format(app))
    else:    
        bashCommand = "singularity run  --overlay {0} -C -H {1}:/temp_home {2}".format(OVERLAY_IMAGE,home,IMAGE_TAR_FILE)
        try:
            subprocess.check_call([bashCommand],shell=True)
        except subprocess.CalledProcessError:
            print("Error running image '{0}'".format(IMAGE_TAR_FILE))

def download(IMAGE_TAR_FILE, filename):
    home = os.environ['HOME']
    current_dir = os.getcwd()
    bashCommand = "singularity run  -B {0}:{1} --overlay {2} -C -H {3}:/temp_home {4} download {5}".format(current_dir,MOUNT_DIR,OVERLAY_IMAGE, home, IMAGE_TAR_FILE, filename)
    try:
        subprocess.check_call([bashCommand],shell=True)
    except subprocess.CalledProcessError:
        print("Error downloading '{0}'".format(filename))

def upload(IMAGE_TAR_FILE, filename):
    home = os.environ['HOME']
    current_dir = os.getcwd()
    bashCommand = "singularity run  -B {0}:{1} --overlay {2} -C -H {3}:/temp_home {4} upload {5}".format(current_dir,MOUNT_DIR,OVERLAY_IMAGE, home, IMAGE_TAR_FILE, filename)
    try:
        subprocess.check_call([bashCommand],shell=True)
    except subprocess.CalledProcessError:
        error_out("Error uploading '{0}' to '{1}".format(filename,IMAGE_DIR))

def destroy(IMAGE_DIR):
    bashCommand = "rm -rf {}".format(IMAGE_DIR)
    try:
        subprocess.check_call([bashCommand],shell=True)
    except subprocess.CalledProcessError:
        error_out("Error destroying '{0}' ".format(IMAGE_DIR))

args = sys.argv[1:]
cmd = args[0]

if cmd not in ["setup","run","upload","download"]:
    print("Invalid Commands - only setup/run/download/upload are allowed")
    exit()

if cmd=="setup":
    rpz_file, IMAGE_DIR = args[1:]
    if not os.path.exists(IMAGE_DIR):
        os.makedirs(IMAGE_DIR)
    os.chdir(IMAGE_DIR)
    rpz_file = "../" + rpz_file
    setup(rpz_file)
elif cmd=="run":
    app = None
    IMAGE_DIR = args[1]
    if len(args) == 3:
        app = args[2]
    os.chdir(IMAGE_DIR)
    run(IMAGE_TAR_FILE,app)
elif cmd in ["upload","download"]:
    IMAGE_DIR,filename = args[1:]
    os.chdir(IMAGE_DIR)
    if not filename:
        print("output file missing!")
    globals()[cmd](IMAGE_TAR_FILE,filename)
elif cmd=="destroy":
     IMAGE_DIR = args[1]
     destroy(IMAGE_DIR)

