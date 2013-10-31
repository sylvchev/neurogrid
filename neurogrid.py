#! /usr/bin/env python

import threading, paramiko, time, subprocess, os, socket, sys
import numpy as np 
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure

#global vars to be shared by threads
LOCK = threading.Lock()
START_TIME = ""
PORT = 22
PASSWORD = "?l1sv?"
PROGRAM_FILE = []
T_PAR_TEMPLATE = ['1.0 p_connect\n', '1.0 w\n', '0.0    sigw0.01\n', '0.2    wmax\n', '0.01   ap\n', '-0.085 am\n', '16.8   taup\n', '33.7   taum\n']
T_CALC_FILE = ""
LOCAL_DIR = ""
REMOTE_DIR = ""
PKEYF= ""
MAX_TRYS = 5
NUMBER_OF_CALC = 1
STATE_LIST = []
PAR_DATA = []
COMP_LIST = []
TRY_LIST = []


def getStartTime():
	st_time = str(time.localtime().tm_year) + "-" + str(time.localtime().tm_mon) + "-" + str(time.localtime().tm_mday) + "-" + str(time.localtime().tm_hour) + "-" + str(time.localtime().tm_min) + "-" + str(time.localtime().tm_sec)
	return st_time


def getCurrentDir():
#finds the current location of the script
	path = os.path.realpath(__file__)

	#change it to program name
	name = "code.py"

	j=path.find(name)
	path=path[:j]
	return path


def printOne(ip, stuf, text):
#function for debug printing
#prints only 1 client data, instead of all
#not used
	if ip == "dell148":
		print text, ">>>>>>>", stuf

def getCPUCoreNumber(ip, user):
#finds out how many cores the cpu of the remote system has by reading lscpu output

	data = executeLine(ip, user, "lscpu")
	names = ["Core(s) per socket:", "Coeur(s) par support CPU :"]

	#find and strip the line containing core number
	for name in names:
		if name in data:
			leng = len(name)
			for line in data.split("\n"):
				if line[:leng]==name:
					data=line
		
	f_data=int(float(data[leng:]))

	return f_data


def setSettings(file_data):
#sets the settings as written in settings file

	global PROGRAM_FILE, REMOTE_DIR, LOCAL_DIR, PORT, PKEYF, T_CALC_FILE, MAX_TRYS, NUMBER_OF_CALC

	for i in file_data:
		j=0
		if "remote_dir" in i:
			j=i.find("=")+1
			REMOTE_DIR = i[j:].strip()
		elif "program_dir" in i:
			j=i.find("=")+1
			LOCAL_DIR = i[j:].strip()
		elif "program_files" in i:
			j=i.find("=")+1 
			PROGRAM_FILE = i[j:].split(", ")
		elif "pkey_dir" in i:
			j=i.find("=")+1
			PKEYF = i[j:].strip()
		elif "port" in i:
			j=i.find("=")+1
			PORT = int(i[j:].strip())
		elif "output_file" in i:
			j=i.find("=")+1
			T_CALC_FILE = i[j:].strip()
		elif "max_trys" in i:
			j=i.find("=")+1
			MAX_TRYS = int(i[j:].strip())			


def readFile(location):
#reads and returns data from file as a list

	data = []
	f = open(location)

	for i in f:
		if not(i =="" or i ==" " or i == "\n"):
			data.append(i.strip("\n"))
	f.close()

	return data


def frange(start, end=None, inc=None):
#a range function, that does accept float increments

	if end == None:
		end = start + 0.0
		start = 0.0
	else: start += 0.0 # force it to be a float

	if inc == None:
		inc = 1.0

	count = int((end - start) / inc)
	if start + count * inc != end:
		# need to adjust the count.
		# AFAIKT, it always comes up one short.
		count += 1

	L = [None,] * count
	for i in xrange(count):
		L[i] = start + i * inc

	return L

def createPars(par_range):
#create a list for each parameter type and adds them to a list

	j=[]
	par_list=[]

	for i in par_range:
		i=i.split(" ")

		#checks if it should create a int or float list
		if "." in i[0] or "." in i[1] or "." in i[2]:
			k=frange(float(i[0]), float(i[1])+float(i[2]), float(i[2]))
		else:
			k=range(int(i[0]), int(i[1])+int(i[2]), int(i[2]))

		#changes that each parameter would be in its own list to create groups 
		for l in range(len(k)):
			k[l]=[k[l]]
		j.append(k)


	#creates groups of parameters(list) and puts them in a final list
	temp1=j[0]
	temp2=[]
	temp3=[]
	temp4=[]

	for k in range(len(j)-1):
		temp2=j[k+1]
		temp3=[]
		for i in temp1:
			for l in temp2:
				temp4 = i + l
				temp3.append(temp4)
		temp1 = temp3
	
	par_list=temp1
	return par_list


	
		
	

def createChecks(par_len):
#creates checks used for parameter assignment
#these list are the same length as parameter group list

	states=[]
	comp=[]
	trys=[]

	states.append(0)
	states=states*par_len
	comp.append(0)
	comp=comp*par_len
	trys.append(0)
	trys=trys*par_len

	return states, comp, trys


def writeToFile(data, location, typ):
#writes data to local file

	f = open(location, typ)

	for i in data:
		f.write(i)

	f.close()

def assignPar():
#assigns which parameter group should a client use

	LOCK.acquire()

	#check what is the current maximum number on clients calculatint 1 parameter group
	max_st=max(STATE_LIST)
	
	#check each parameter in order of least being worked on
	# if its calculation has been compleated or if its been tried to calculate too many times return None

	for i in range(max_st + 1):
		for l in range(len(STATE_LIST)):
			if STATE_LIST[l] == i:
				if COMP_LIST[l] < NUMBER_OF_CALC and TRY_LIST[l] < MAX_TRYS:

					STATE_LIST[l] += 1
					TRY_LIST[l] += 1

					LOCK.release()
					return PAR_DATA[l], l

	LOCK.release()
	return None, None

def copyFileToRemMachine(ip, username, loc_dir, rem_dir, file_name):
#copys file to a remote machine
	key = paramiko.RSAKey.from_private_key_file(PKEYF, password=PASSWORD)
	c=paramiko.Transport((ip, PORT))
	c.connect(username=username, pkey=key)
	tp=paramiko.SFTPClient.from_transport(c) 
	tp.put(os.path.join(loc_dir, file_name), os.path.join(rem_dir, file_name))
	
	c.close()

def getRemFile(ip, username, rem_dir, loc_dir):
#copys file from remote machine to local
	key = paramiko.RSAKey.from_private_key_file(PKEYF, password=PASSWORD)
	c=paramiko.Transport((ip, PORT))
	c.connect(username=username, pkey=key)
	tp=paramiko.SFTPClient.from_transport(c)
	tp.get(remotepath=rem_dir, localpath=loc_dir)
	c.close()

def getRemFileData(ip, username, rem_dir, file_name):
#reads the data from a file on a remote machine and stores it in a string
#not used
	ssh = paramiko.SSHClient()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	ssh.connect(ip, username=username, password=PASSWORD, key_filename=PKEYF, timeout=10)
	sftp = ssh.open_sftp()
	sftp_file = sftp.open(os.path.join(rem_dir, file_name), "r")
	data=""
	for i in sftp_file:
		data=data+i
	sftp_file.close()
	sftp.close()
	ssh.close()
	return data

def putDataInRemFile(ip, username, rem_dir, file_name, data):
#writes data to a file on remote machine. creates a new one and overwrites
	ssh = paramiko.SSHClient()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	ssh.connect(ip, username=username, password=PASSWORD, key_filename=PKEYF, timeout=10)
	sftp = ssh.open_sftp()
	sftp_file = sftp.open(os.path.join(rem_dir, file_name), "wb")
	for i in data:
		sftp_file.write(i)
	sftp_file.close()
	sftp.close()
	ssh.close()


def executeLine(ip, username, command):
#executes linux command on a remote machine and waits for it to finish. returns output
	#print "command is:", command, "||| at", ip
	e=paramiko.SSHClient()
	e.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	e.connect(ip, username=username, password=PASSWORD, key_filename=PKEYF)
	stdin, stdout, stderr = e.exec_command(command)
	channel = stdout.channel
	status = stdout.channel.recv_exit_status()

	#if program didn't close normaly
	if status != 0:
		print "command:", command, "crashed with", status, stderr.read()

	e.close()
	return stdout.read()

def ifAllGreaterOrEqual(items, var):
#checks if all items in list are greater or equal of given number
	for i in items:
		if i < var:
			return False
	return True

def cleanUpRemote(user, ip, core):
#trys to delete all files copied and created on remote machine
	executeLine(ip, user, "rm -fr " + os.path.join(REMOTE_DIR, core))
	


def cleanUpLocal():
#archives the results and deletes all unnecesary files
	subprocess.call("cd " +  LOCAL_DIR + " &&" + "tar -zcf ./" + START_TIME + ".tar.gz" + " " +  START_TIME, shell=True)
	subprocess.call("rm -rf " + os.path.join(LOCAL_DIR, START_TIME), shell=True)


def createGraphs():
#creates graphs from the results
	findDataFiles()


def findDataFiles():
#finds all results files in data folder tree a creates a graph for each one
	for root, dirs, files in os.walk(os.path.join(LOCAL_DIR, START_TIME)):
		#if there are files
		if files:
			for data_file in files:
				if data_file[(len(data_file)-4):] == ".txt" in data_file:
					drawGraph(root, data_file)
					
	

def drawGraph(input_location, data_file):
#creates a graph from a data stored in file
	data=readFile(os.path.join(input_location, data_file))
	x_array=[]
	y_array=[]
	for i in data:
		if i != "" and i != " " and i != "\n":
			temp=i.split(" ")
			x_array.append(temp[0])
			y_array.append(temp[1])
			
	x_array=np.array(x_array)
	y_array=np.array(y_array)
	fig = Figure()
	canvas = FigureCanvas(fig)
	ax = fig.add_subplot(111)
	ax.plot(x_array, y_array)
	ax.set_title("Number of working ants at each time")
	ax.grid(True)
	ax.set_xlabel("time")
	ax.set_ylabel("working ants")
	canvas.print_figure(os.path.join(input_location, data_file + ".png"))

def reduceData(input_location, ip):
#removes 3 colums of data from file by creating a temporary file and renaming it
	read_file = open(os.path.join(input_location, ip + ".txt"), "r")
	write_file = open(os.path.join(input_location, ip + ".tmp"), "w+")
	for line in read_file:
		if line != "" and line != " " and line != "\n":
			temp=line.strip("\n")
			temp=temp.split(" ")
			reduced_line = temp[0] + " " + temp[2] + "\n"
			write_file.write(reduced_line)
	read_file.close()
	write_file.close()
	subprocess.call("rm -rf " + os.path.join(input_location, ip + ".txt"), shell=True)
	subprocess.call("mv " + os.path.join(input_location, ip + ".tmp")  + " " + os.path.join(input_location, ip + ".txt"), shell=True)
	

def connectAndLaunch(ip, user, core):
#launches all the functions necessary for the thread
	
	#check if everything has been completed
	if not(ifAllGreaterOrEqual(COMP_LIST, NUMBER_OF_CALC)):
		
		#removes previous temporary folder if it exists
		executeLine(ip, user, "rm -f " + os.path.join(REMOTE_DIR, core, T_CALC_FILE))

		#get a parameter, if there are none close the thread and clean up
		par, nmb = assignPar()
		if par == None and nmb == None:
			cleanUpRemote(user, ip, core)
			return False
		
		#write the parameters to remote configuration file
		t_par=list(T_PAR_TEMPLATE)
		t_par[0] = str(par[3]) + " p_connect\n"
		t_par[1] = str(par[4]) + " w\n"
		putDataInRemFile(ip, user, os.path.join(REMOTE_DIR, core), PROGRAM_FILE[2], t_par)

		#execute the program and wait for it to finish with the remaining parameters passed down
		executeLine(ip, user,  "cd " + os.path.join(REMOTE_DIR, core) +" && ./" + PROGRAM_FILE[0] + " " + str(par[0]) + " " + str(par[1]) + " " + str(par[2]))
		executeLine(ip, user, "cd")

		#create a folder on local machine and store the remote results in it
		file_dir = os.path.join(LOCAL_DIR, START_TIME, str(par[0]), str(par[1]), str(par[2]), str(par[3]), str(par[4]))
		subprocess.call("mkdir -p " + file_dir, shell=True)
		getRemFile(ip, user, os.path.join(REMOTE_DIR, core, T_CALC_FILE), os.path.join(file_dir, ip + "c" + core +".txt"))

		#remove the unnecessary information in results file to save space
		reduceData(file_dir, ip + "c" + core)

		#change the parameter checks that the thread compleated the calculation and is no longer calculating
		LOCK.acquire()
		COMP_LIST[nmb] = COMP_LIST[nmb] + 1
		STATE_LIST[nmb] = STATE_LIST[nmb] - 1
		LOCK.release()

		#print what has been done
		print ip, "core", core, "completed", par, "calculation, %d%% work left" %(100 - calcWorkPercent())
		return True
	
	#if there is no more work close the thread and clean up
	else:
		cleanUpRemote(user, ip, core)
		return False
	
def getRemotePID(user, ip):
#gets the PID of the program launched on remote machine
#not used
	proc=executeLine(ip, user, "ps ax | grep " + PROGRAM_FILE[0])
	data=[]
	for i in proc.split("\n"):
		if i != "" and i != " ":
			data.append(i)
	clean_data=[]
	for i in data:
		i=i.split(" ")
		temp=[]
		for j in i:
			if j != "" and j != " ":
				temp.append(j)
		clean_data.append(temp)
	ids=[]
	for i in clean_data:
		if "Rs" in i:
			ids.append(i[0])

	return ids

def killAllProcesses(clients, threads):
#kills all processes of the launched program
#not used
	for i in threads:
		i.be_on=False
	for l in clients:
		user, ip = l.split(" ")
		ids=getRemotePID(user, ip)
		for j in ids:
			print "killed: ", j, ip
			void=executeLine(ip, user, "kill " + j)

def inputData(clients, threads):
#waits for user input
#not used
	while True:
		c_input=raw_input()
		if c_input == "i" or c_input == "interrupt":
			killAllProcesses(clients, threads)
			return -1
		elif c_input == "e" or c_input == "exit":
			return 0

def wakeOnLAN(clients):
#passes an wakeonlan command to wake up the clients
	wlan=False

	for i in range(len(clients)):
		void1, void2, mac = clients[i].split()
		output = subprocess.call("wakeonlan " + mac, shell=True)
		if output == 0:
			wlan=True

	#returns if wake on lan succeeded
	return wlan

def calcWorkPercent():
#calculates the current progress in %
	be_on = True
	data_comp=0
	LOCK.acquire()
	data_amount = len(COMP_LIST) * NUMBER_OF_CALC
	for i in COMP_LIST:
		if i >= NUMBER_OF_CALC:
			data_comp += NUMBER_OF_CALC
		else:
			data_comp += i
	LOCK.release()
	percent = float(data_comp)/float(data_amount) * 100
	percent = int(round(percent, 0))
	return percent

			

class cThread(threading.Thread):
#class which creates a thread for each remote machine
	def __init__ (self, ip, user, core):
		threading.Thread.__init__(self)
		self.ip = ip
		self.user = user
		self.core = core
		self.be_on = True
	def run(self):
	#thread initialization
		
		#creates a folder on remote machine and copys all the program files to it
		executeLine(self.ip, self.user, "mkdir -p " + os.path.join(REMOTE_DIR, self.core))
		for i in PROGRAM_FILE:
			try:
				copyFileToRemMachine(self.ip, self.user, LOCAL_DIR, os.path.join(REMOTE_DIR, self.core), i)

			#catches a random usualy not fatal error
			except IOError:
				print " copy error @", self.ip, self.user, LOCAL_DIR, os.path.join(REMOTE_DIR, self.core), i

		#sets executing rights to program file
		executeLine(self.ip, self.user, "chmod 755 " + os.path.join(REMOTE_DIR, self.core, PROGRAM_FILE[0]))
		
		#begins calculations and stop then there is no more work
		while self.be_on:                                
			temp = connectAndLaunch(self.ip, self.user, self.core)
			if self.be_on:
				self.be_on = temp


def main():
#main functions that launches the others
	global STATE_LIST, PAR_DATA, COMP_LIST, TRY_LIST, START_TIME

	START_TIME = getStartTime()

		
	#reads the settings files in the same dir as program
	main_dir=getCurrentDir()
	setting_data=readFile(os.path.join(main_dir, "settings.txt"))
	setSettings(setting_data)
	clients = readFile(os.path.join(main_dir, "clients.txt"))
	PAR_DATA = readFile(os.path.join(main_dir, "parameters.txt"))

	#creates the parameters groups and checks
	PAR_DATA = createPars(PAR_DATA)
	STATE_LIST, COMP_LIST, TRY_LIST = createChecks(len(PAR_DATA))

	#wakes up all computers
	wlan = False
	wlan = wakeOnLAN(clients)
	if wlan == True:		
		#waits a certain time for computers to wake up
		time.sleep(180)

	#creates a thread for each remotes machines core
	thread_list=[]
	for i in range(len(clients)):
		user, ip, mac = clients[i].split()
		cpu_cores = 0

		try:
			cpu_cores=getCPUCoreNumber(ip, user)

		#catches an error that shows that the clients is unreachable
		except socket.error:
			print "No route to client:", ip
		
		for core in range(cpu_cores):
			t = cThread(ip, user, str(core))
			thread_list.append(t)
			t.start()

	#prints how manny threads have been created
	print "number of threads:", len(thread_list)
	
	#waits for all threads to finish
	for t in thread_list:
		t.join()
 	
	#creates graphs and archives the results	
	print "finished calculation"
	createGraphs()
	print "finished graph creation"
	cleanUpLocal()	
	print "everything finished"

#launches main function
if __name__ == "__main__":
	main()



