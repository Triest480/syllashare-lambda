import pymysql
import json
import os
import uuid
import time
import datetime
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools
from apiclient.discovery import build

def updateGoogleEvents(events, refreshToken, userID):
    googleKey = os.environ["googleKey"]
    googleSecret = os.environ["googleSecret"]
    credentials = oauth2client.client.GoogleCredentials(None, googleKey, googleSecret, refreshToken, None,"https://accounts.google.com/o/oauth2/token", 'syllashare.com')
    http = httplib2.Http()
    http = credentials.authorize(http)
    service = build('calendar', 'v3', http=http)
    for event in events:
        googleEvent = {
            'summary': event.name,
            'description': 'Description',
            'start': {
                'dateTime': datetime.utcfromtimestamp(int(event.time)).strftime('%Y-%m-%d %H:%M:%S')
            },
            'end': {
                'dateTime': datetime.utcfromtimestamp(int(event.time + event.mins * 60 * 1000)).strftime('%Y-%m-%d %H:%M:%S')
            },
            'reminders': {
                'useDefault': True
            }
        }
        event = service.events().insert(calendarId='primary', body=event).execute()

def getUser(cursor, userID):
    cursor.execute("""SELECT u.id AS id, u.username AS username, u.first_name AS firstName, u.last_name AS lastName, u.pic_key AS picKey, 
        s.name AS schoolName, s.city AS schoolCity, s.state AS schoolState, s.pic_key AS schoolPicKey
        FROM user_data_user u LEFT JOIN user_data_school s ON u.school_id=s.name
        WHERE u.id=%s""", (userID))
    for (userID, username, firstName, lastName, picKey, schoolName, schoolCity, schoolState, schoolPicKey) in cursor:
        schoolDict = None
        if (schoolName is not None):
            schoolDict = {
                "name": schoolName,
                "city": schoolCity,
                "state": schoolState,
                "picKey": schoolPicKey
            }
        return { "id": userID, "username": username, "firstName": firstName, "lastName": lastName, "picKey": picKey, "school": schoolDict }
    return None

def canRead(cursor, groupName, userID):
    cursor.execute('SELECT g.readPrivate, gu.accepted FROM Groups g LEFT JOIN GroupsToUsers gu ON g.name=gu.groupName AND gu.userID=%s WHERE g.name=%s', (userID, groupName))
    row = cursor.fetchone()
    return (not row[0] or row[1])

def canWrite(cursor, groupName, userID):
    cursor.execute('SELECT g.writePrivate, gu.accepted, gu.writable FROM Groups g LEFT JOIN GroupsToUsers gu ON g.name=gu.groupName AND gu.userID=%s WHERE g.name=%s', (userID, groupName))
    row = cursor.fetchone()
    return (not row[0] or (row[1] and row[2]))
    
def isInGroup(cursor, groupName, userID):
    return (cursor.execute('SELECT groupName FROM GroupsToUsers WHERE groupName=%s AND userID=%s AND accepted=1', (groupName, userID)) > 0)
    
def createGroup(connection, cursor, groupName, readPrivate, writePrivate, userID):
    if cursor.execute('INSERT INTO Groups VALUES (%s, %s, %s)', (groupName, str(1 if readPrivate else 0), str(1 if writePrivate else 0))) > 0:
        if cursor.execute('INSERT INTO GroupsToUsers VALUES (%s, %s, %s, %s)', (groupName, userID, str(1), str(1))) > 0:
            connection.commit()
            return { "name": groupName, "readPrivate": readPrivate, "writePrivate": writePrivate }
        return { "errMsg": "Failed to add user into group" }
    return { "errMsg": "Failed to create group" }
    
    
def joinGroup(connection, cursor, groupName, userID):
    if cursor.execute('SELECT readPrivate, writePrivate FROM Groups WHERE name=%s', (groupName)) > 0:
        row = cursor.fetchone()
        readPrivate = row[0]
        writePrivate = row[1]
        if readPrivate:
            if cursor.execute('UPDATE GroupsToUsers SET accepted=%s WHERE groupName=%s AND userID=%s', (str(1), groupName, userID)) <= 0:
                return { "errMsg": "User not invited" }
        else:
            cursor.execute('INSERT INTO GroupsToUsers VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE accepted=%s', (groupName, userID, str(1), str(0 if writePrivate else 1), str(1)))
        connection.commit()
        cursor.fetchall()
        group = getGroup(connection, cursor, groupName, userID)["group"]
        user = getUser(cursor, userID)
        cursor.execute("SELECT writable FROM GroupsToUsers WHERE groupName=%s AND userID=%s", (groupName, userID))
        writable = cursor.fetchone()[0]
        user["writable"] = writable
        return { "group": group, "user": user, "userID": userID, "groupName": groupName }
    return { "errMsg": "Group not found" }


def leaveGroup(connection, cursor, groupName, userID):
    group = getGroup(connection, cursor, groupName, userID)["group"]
    if cursor.execute('DELETE FROM GroupsToUsers WHERE groupName=%s AND userID=%s', (groupName, userID)) > 0:
        connection.commit()
        return { "group": group, "user": getUser(cursor, userID), "userID": userID, "groupName": groupName }
    return { "errMsg": "Not in or have not been invited to group" }
    
def kickFromGroup(connection, cursor, groupName, kickUserID, userID):
    if canWrite(cursor, groupName, userID):
        group = getGroup(connection, cursor, groupName, userID)["group"]
        if cursor.execute('DELETE FROM GroupsToUsers WHERE groupName=%s AND userID=%s', (groupName, kickUserID)) > 0:
            connection.commit()
            return { "group": group, "user": getUser(cursor, kickUserID), "userID": kickUserID, "groupName": groupName }
        return { "errMsg": "Not in or have not been invited to group" }
    return {"errMsg": "Cannot kick from group you are not in" }
    
def setGroupAccess(connection, cursor, groupName, setUserID, writable, userID):
    if canWrite(cursor, groupName, userID):
        if cursor.execute('UPDATE GroupsToUsers SET writable=%s WHERE groupName=%s AND userID=%s', (str(1 if writable else 0), groupName, setUserID)) <= 0:
            return { "errMsg": "User not invited" }
        connection.commit();
        return { "userID": setUserID, "writable": writable }
    return { "errMsg": "You can't set access of someone in a group you're not in" }
    
def inviteToGroup(connection, cursor, groupName, inviteToUserID, writable, invokerUserID):
    if canWrite(cursor, groupName, invokerUserID):
        if cursor.execute('INSERT INTO GroupsToUsers VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE writable=%s', (groupName, inviteToUserID, str(0), str(1 if writable else 0), str(1 if writable else 0))) > 0:
            connection.commit()
            group = getGroup(connection, cursor, groupName, invokerUserID)["group"]
            user = getUser(cursor, inviteToUserID)
            user["writable"] = writable
            return { "group": group, "user": user, "userID": inviteToUserID, "groupName": groupName }
        return { "errMsg": "Failed to invite user" }
    return { "errMsg": "You can't invite someone to a group you're not in" }
    
    
def createChat(connection, cursor, groupName, chatName, chatSubject, userID):
    if canWrite(cursor, groupName, userID):
        chatID = uuid.uuid4()
        if cursor.execute('INSERT INTO Chats VALUES (%s, %s, %s, %s)', (str(chatID), groupName, chatName, chatSubject)) > 0:
            connection.commit()
            return { "id": str(chatID), "name": chatName, "subject": chatSubject, "groupName": groupName }
        return { "errMsg": "Could not create group" }
    return { "errMsg": "User is not in group" }
  
    
def createMessage(connection, cursor, chatID, text, objKey, creationEpochSecs, userID):
    #Check if user is part of group that the chat belongs to
    if cursor.execute("""SELECT c.groupName FROM Chats c WHERE c.id=%s""", (chatID)) > 0:
        groupName = cursor.fetchone()[0]
        if canRead(cursor, groupName, userID):
            msgID = uuid.uuid4()
            if cursor.execute("""INSERT INTO Messages VALUES (%s, %s, %s, %s, %s, %s)""", (str(msgID), chatID, text, objKey, str(creationEpochSecs), userID)) > 0:
                connection.commit()
                msg = { "id": str(msgID), "text": text, "objKey": objKey, "creationEpochSecs": creationEpochSecs, "chatID": chatID, "senderID": userID }
                return { "message": msg, "sender": getUser(cursor, userID), "chatID": chatID }
            return { "errMsg": "Could not add message" }
        return { "errMsg": "You don't have access to this group" }
    return { "errMsg": "User not in group" }


    
def getGroups(connection, cursor, userID):
    cursor.execute("""SELECT g.name, g.readPrivate, g.writePrivate FROM GroupsToUsers gu INNER JOIN Groups g ON gu.groupName=g.name LEFT JOIN Classes c ON c.id=g.name WHERE gu.userID=%s AND c.id IS NULL""", (userID))
    groups = []
    for (groupName, readPrivate, writePrivate) in cursor:
        groups.append({ "group": { "name": groupName, "readPrivate": readPrivate, "writePrivate": writePrivate } })
    for group in groups:
        groupContents = getGroup(connection, cursor, group["group"]["name"], userID)
        group["group"]["users"] = groupContents["group"]["users"]
        group["group"]["chats"] = groupContents["group"]["chats"]
        group["accepted"] = groupContents["accepted"]
        group["writable"] = groupContents["writable"]
    return groups
            

def getGroup(connection, cursor, groupName, userID):
    if cursor.execute("""SELECT g.readPrivate, g.writePrivate, gu.accepted, gu.writable, c.courseID FROM Groups g LEFT JOIN GroupsToUsers gu ON gu.groupName=g.name AND gu.userID=%s LEFT JOIN Classes c ON c.id=g.name WHERE g.name=%s""", (userID, groupName)) > 0:
        row = cursor.fetchone()
        readPrivate = row[0]
        writePrivate = row[1]
        groupAccepted = row[2]
        groupWritable = row[3]
        courseID = row[4]
        if (not readPrivate or groupAccepted is not None):
            events = getEvents(connection, cursor, groupName)
            group = {
                "name": groupName,
                "readPrivate": readPrivate,
                "writePrivate": writePrivate,
                "users": [],
                "chats": [],
                "events": events,
                "courseID": courseID
            }
            cursor.execute("""SELECT gu.userID, gu.accepted, gu.writable FROM GroupsToUsers gu WHERE gu.groupName=%s""", (groupName))
            userQueryRes = cursor.fetchall()
            for (userID, accepted, writable) in userQueryRes:
                user = getUser(cursor, userID)
                user["accepted"] = accepted
                user["writable"] = writable
                group["users"].append(user)
            cursor.execute("""SELECT c.id, c.name, c.subject FROM Chats c WHERE c.groupName=%s""", (groupName))
            for (chatID, chatName, chatSubject) in cursor:
                group["chats"].append({ "id": chatID, "name": chatName, "subject": chatSubject })
            return { "accepted": groupAccepted, "writable": groupWritable, "group": group }
        print("You don't have access to this group!")
        return { "errMsg": "You don't have access to this group!" }
    print("Group: ", groupName, " with member ", userID, " does not exist")
    return { "errMsg": "User not a member of group or group does not exist" }


def getMessages(connection, cursor, chatID, userID):
    if cursor.execute("""SELECT c.groupName FROM Chats c WHERE c.id=%s""", (chatID)) > 0:
        groupName = cursor.fetchone()[0]
        if canRead(cursor, groupName, userID):
            senderIDs = {}
            messages = []
            cursor.execute("""SELECT id, text, objKey, creationEpochSecs, senderID FROM Messages WHERE chatID=%s ORDER BY creationEpochSecs DESC""", (chatID))
            for (id, text, objKey, creationEpochSecs, senderID) in cursor:
                senderIDs[senderID] = True
                messages.append({ "id": id, "text": text, "objKey": objKey, "creationEpochSecs": creationEpochSecs, "chatID": chatID, "senderID": senderID })
            senders = []
            for senderID in senderIDs:
                senders.append(getUser(cursor, senderID))
            return { "messages": messages, "senders": senders }
        return { "errMsg": "user does not have access" }
    return { "errMsg": "User not in group" }
    
    
def searchGroups(connection, cursor, query, userID):
    resp = []
    if cursor.execute("""SELECT g.name, g.readPrivate, g.writePrivate FROM Groups g LEFT JOIN Classes c ON g.name=c.id
        WHERE c.id IS NULL AND LCASE(g.name) LIKE %s ORDER BY LENGTH(g.name), g.name LIMIT 50""", (query + '%')) > 0:
            for (name, readPrivate, writePrivate) in cursor:
                resp.append({"name": name, "readPrivate": readPrivate, "writePrivate": writePrivate})
    return resp
    
def createClass(connection, cursor, courseID, schoolName, term, year, courseName, teacherName, timeStr, writePrivate, userID):
    if (cursor.execute("""SELECT name FROM Courses WHERE id=%s AND schoolName=%s""", (courseID, schoolName))) == 0:
        cursor.execute("""INSERT INTO Courses VALUES (%s, %s, %s)""", (courseID, courseName, schoolName))
    cursor.execute("""INSERT INTO Teachers VALUES (%s, %s) ON DUPLICATE KEY UPDATE schoolName=%s""", (teacherName, schoolName, schoolName))
    classID = uuid.uuid4()
    createGroup(connection, cursor, str(classID), False, writePrivate, userID)
    if cursor.execute("""INSERT INTO Classes VALUES (%s, %s, %s, %s, %s, %s)""", (str(classID), teacherName, term, str(year), timeStr, courseID)) > 0:
        connection.commit()
        return getClass(connection, cursor, str(classID), userID)
        
def getEvents(connection, cursor, groupName):
    cursor.execute("""SELECT e.id, e.name, e.time, e.mins, e.priority, co.id FROM Events e LEFT JOIN Classes c ON c.id=e.groupName LEFT JOIN Courses co ON c.courseID=co.id WHERE e.groupName=%s""", (groupName))
    events = []
    for (id, name, time, mins, priority, classID) in cursor:
        events.append({ "id": id, "name": name, "time": time, "mins": mins, "groupName": groupName, "priority": priority, "classID": classID })
    return events
    
def getUserEvents(connection, cursor, userID):
    cursor.execute("""SELECT groupName FROM GroupsToUsers WHERE userID=%s AND accepted=1""", (userID))
    groupNames = cursor.fetchall()
    events = []
    for (groupName) in groupNames:
        events += getEvents(connection, cursor, groupName)
    return events

def updateEvents(connection, cursor, groupName, events):
    idMap = {}
    for event in events:
        eventID = None
        if "id" in event and event["id"] is not None:
            eventID = event["id"]
            cursor.execute("UPDATE Events SET name=%s, time=%s, mins=%s, priority=%s WHERE id=%s", (event["name"], event["time"], event["mins"], str(event["priority"]), event["id"]))
        else:
            eventID = str(uuid.uuid4())
            cursor.execute("INSERT INTO Events VALUES (%s, %s, %s, %s, %s, %s)", (eventID, event["name"], event["time"], event["mins"], groupName, str(event["priority"])))
        idMap[eventID] = True
    connection.commit()
    
    evts = getEvents(connection, cursor, groupName)
    results = []
    for evt in evts:
        if (evt["id"] in idMap):
            results.append(evt)
    return { "groupName": groupName, "events": results }
    
def deleteEvents(connection, cursor, groupName, eventIDs):
    idMap = {}
    for id in eventIDs:
        idMap[id] = True
    evts = getEvents(connection, cursor, groupName)
    results = []
    for evt in evts:
        if (evt["id"] in idMap):
            results.append(evt)
    formatStrings = ','.join(['%s'] * len(eventIDs))
    if cursor.execute("DELETE FROM Events WHERE id IN (%s)" % formatStrings, tuple(eventIDs)) > 0:
        connection.commit()
        return { "groupName": groupName, "events": results }
    return { "errMsg": "Failed to delete ids" }
    
def searchTeachers(connection, cursor, query, userID):
    teachers = []
    if cursor.execute("SELECT school_id FROM user_data_user WHERE id=%s", (userID)) > 0:
        schoolName = cursor.fetchone()[0]
        if schoolName is not None:
            cursor.execute("""SELECT t.name, s.name, s.city, s.state, s.pic_key FROM Teachers t
                INNER JOIN user_data_school s ON t.schoolName=s.name 
                WHERE t.schoolName=%s AND LCASE(t.name) LIKE %s 
                ORDER BY LENGTH(t.name), t.name LIMIT 50""", (schoolName, query + '%'))
        else:
            cursor.execute("""SELECT t.name, s.name, s.city, s.state, s.pic_key FROM Teachers t
                LEFT JOIN user_data_school s ON t.schoolName=s.name 
                WHERE LCASE(t.name) LIKE %s 
                ORDER BY LENGTH(t.name), t.name LIMIT 50""", (query + '%'))
        for (teacherName, schoolName, schoolCity, schoolState, schoolPicKey) in cursor:
            school = None
            if schoolName is not None:
                school = {
                    "name": schoolName,
                    "city": schoolCity,
                    "state": schoolState,
                    "picKey": schoolPicKey
                }
            teachers.append({
                "name": teacherName,
                "school": school
            })
    return teachers
    
def searchCourses(connection, cursor, query, userID):
    if cursor.execute("SELECT school_id FROM user_data_user WHERE id=%s", (userID)) > 0:
        schoolName = cursor.fetchone()[0]
    if schoolName is None:
        cursor.execute("""SELECT co.id, co.name, s.name, s.city, s.state, s.pic_key FROM Courses co 
            LEFT JOIN user_data_school s ON co.schoolName=s.name 
            WHERE LCASE(co.id) LIKE %s OR LCASE(co.name) LIKE %s 
            ORDER BY LENGTH(co.id), co.id LIMIT 50""", (query + '%', query + '%'))
    else:
        cursor.execute("""SELECT co.id, co.name, s.name, s.city, s.state, s.pic_key FROM Courses co 
            INNER JOIN user_data_school s ON co.schoolName=s.name 
            WHERE s.name=%s AND (LCASE(co.id) LIKE %s OR LCASE(co.name) LIKE %s) 
            ORDER BY LENGTH(co.id), co.id LIMIT 50""", (schoolName, query + '%', query + '%'))
    courses = []
    for (courseID, courseName, schoolName, schoolCity, schoolState, schoolPicKey) in cursor:
        school = None
        if schoolName is not None:
            school = {
                "name": schoolName,
                "city": schoolCity,
                "state": schoolState,
                "picKey": schoolPicKey
            }
        courses.append({
            "id": courseID,
            "name": courseName,
            "school": school
        })
    return courses
    
    
def getClass(connection, cursor, classID, userID):
    if cursor.execute("""SELECT c.teacherName, c.term, c.year, c.timeStr, co.id, co.name, s.name, s.city, s.state, s.pic_key FROM Classes c 
        INNER JOIN Courses co ON c.courseID=co.id
        LEFT JOIN user_data_school s ON co.schoolName=s.name
        WHERE c.id=%s""", (classID)) > 0:
        for (teacherName, term, year, timeStr, courseID, courseName, schoolName, schoolCity, schoolState, schoolPicKey) in cursor:
            school = None
            if schoolName is not None:
                school = {
                    "name": schoolName,
                    "city": schoolCity,
                    "state": schoolState,
                    "picKey": schoolPicKey
                }
            course = {
                "id": courseID,
                "name": courseName,
                "school": school
            }
            teacher = {
                "name": teacherName
            }
            res = {
                "id": classID,
                "course": course,
                "teacher": teacher,
                "term": term,
                "year": year,
                "timeStr": timeStr,
                "group": getGroup(connection, cursor, classID, userID)
            }
            return res
    return None
    
def getTerm(connection, cursor, schoolName, year, term):
    cursor.execute("""SELECT start, end FROM Terms WHERE schoolName=%s AND term=%s AND (year=%s OR year IS NULL) ORDER BY year LIMIT 1""", (schoolName, term, year))
    for (start, end) in cursor:
        return { "start": start, "end": end }
    
def getClassesForUser(connection, cursor, queryUserID, userID):
    cursor.execute("""SELECT gu.groupName FROM GroupsToUsers gu INNER JOIN Classes c ON gu.groupName=c.id WHERE gu.userID=%s""", (queryUserID))
    groupNames = cursor.fetchall()
    classes = []
    for (groupName) in groupNames:
        classes.append(getClass(connection, cursor, groupName[0], userID))
    return classes
    
def getClassesForCourse(connection, cursor, courseID, userID):
    cursor.execute("""SELECT c.id FROM Classes c WHERE c.courseID=%s""", (courseID))
    classIDs = cursor.fetchall()
    classes = []
    for classID in classIDs:
        classes.append(getClass(connection, cursor, classID[0], userID))
    return classes
    
def updatePersonalEvents(connection, cursor, userID, events):
    if cursor.execute("""SELECT g.name FROM Groups g WHERE name=%s""", (userID)) == 0:
        createGroup(connection, cursor, True, True, userID)
    return updateEvents(connection, cursor, userID, events)
    
def handler(event, context):
    dbHost = os.environ['db_host']
    dbUser = os.environ['db_user']
    dbPwd = os.environ['db_pwd']
    dbDb = os.environ['db_db']
        
    connection = pymysql.connect(user=dbUser, password=dbPwd,
                        host=dbHost,
                        database=dbDb)
    cursor = connection.cursor()
    
    userID = event["cognitoIdentityId"]
    
    print(event)
    args = event["arguments"]
    #python has no switch-case
    if (event["type"] == "CreateGroup"):
        return createGroup(connection, cursor, args["groupName"], args["readPrivate"], args["writePrivate"], userID)
    elif (event["type"] == "JoinGroup"):
        return joinGroup(connection, cursor, args["groupName"], userID)
    elif (event["type"] == "LeaveGroup"):
        if ("kickUserID" in args and args["kickUserID"] is not None):
            return kickFromGroup(connection, cursor, args["groupName"], args["kickUserID"], userID)
        else:
            return leaveGroup(connection, cursor, args["groupName"], userID)
    elif (event["type"] == "InviteToGroup"):
        return inviteToGroup(connection, cursor, args["groupName"], args["inviteToUserID"], args["write"], userID)
    elif (event["type"] == "CreateChat"):
        return createChat(connection, cursor, args["groupName"], args["chatName"], args["chatSubject"], userID)
    elif (event["type"] == "CreateMessage"):
        return createMessage(connection, cursor, args["chatID"], args["text"], args["objKey"], args["creationEpochSecs"], userID)
    elif (event["type"] == "GetGroups"):
        return getGroups(connection, cursor, userID)
    elif (event["type"] == "GetGroup"):
        return getGroup(connection, cursor, args["groupName"], userID)
    elif (event["type"] == "GetMessages"):
        return getMessages(connection, cursor, args["chatID"], userID)
    elif (event["type"] == "SearchGroups"):
        return searchGroups(connection, cursor, args["query"], userID)
    elif (event["type"] == "SetWritable"):
        return setGroupAccess(connection, cursor, args["groupName"], args["setUserID"], args["writable"], userID)
    elif (event["type"] == "CreateClass"):
        return createClass(connection, cursor, args["courseID"], args["schoolName"], args["term"], args["year"], args["courseName"], args["teacherName"], args["timeStr"], args["writePrivate"], userID)
    elif (event["type"] == "UpdateEvents"):
        if ("personal" in args and args["personal"]):
            return updatePersonalEvents(connection, cursor, userID, args["events"])
        else:
            return updateEvents(connection, cursor, args["groupName"], args["events"])
    elif (event["type"] == "DeleteEvents"):
        if ("personal" in args and args["personal"]):
            return deleteEvents(connection, cursor, userID, args["eventIDs"])
        else:
            return deleteEvents(connection, cursor, args["groupName"], args["eventIDs"])
    elif (event["type"] == "SearchCourses"):
        return searchCourses(connection, cursor, args["query"], userID)
    elif (event["type"] == "GetClasses"):
        return getClassesForCourse(connection, cursor, args["courseID"], userID)
    elif (event["type"] == "GetClass"):
        return getClass(connection, cursor, args["classID"], userID)
    elif (event["type"] == "GetUserClasses"):
        return getClassesForUser(connection, cursor, args["userID"], userID)
    elif (event["type"] == "GetUserEvents"):
        return getUserEvents(connection, cursor, args["userID"])
    elif (event["type"] == "SearchTeachers"):
        return searchTeachers(connection, cursor, args["query"], userID)
    elif (event["type"] == "GetTerm"):
        return getTerm(connection, cursor, args["schoolName"], args["year"], args["term"])
    return { "errMsg": "Event not found" }