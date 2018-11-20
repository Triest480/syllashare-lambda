import pymysql
import json
import os
import uuid
import time

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
    print("Leave group called: ", groupName, " - ", userID)
    group = getGroup(connection, cursor, groupName, userID)["group"]
    if cursor.execute('DELETE FROM GroupsToUsers WHERE groupName=%s AND userID=%s', (groupName, userID)) > 0:
        connection.commit()
        return { "group": group, "user": getUser(cursor, userID), "userID": userID, "groupName": groupName }
    print("User not in or not invited to group")
    return { "errMsg": "Not in or have not been invited to group" }
    
def kickFromGroup(connection, cursor, groupName, kickUserID, userID):
    if canWrite(cursor, groupName, userID):
        group = getGroup(connection, cursor, groupName, userID)["group"]
        if cursor.execute('DELETE FROM GroupsToUsers WHERE groupName=%s AND userID=%s', (groupName, kickUserID)) > 0:
            connection.commit()
            return { "group": group, "user": getUser(cursor, kickUserID), "userID": kickUserID, "groupName": groupName }
        print("User not in or not invited to group")
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
    print("Creating msg")
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
    cursor.execute("""SELECT g.name, g.readPrivate, g.writePrivate FROM GroupsToUsers gu INNER JOIN Groups g ON gu.groupName=g.name WHERE gu.userID=%s""", (userID))
    groups = []
    for (groupName, readPrivate, writePrivate) in cursor:
        groups.append({ "group": { "name": groupName, "readPrivate": readPrivate, "writePrivate": writePrivate } })
    for group in groups:
        groupContents = getGroup(connection, cursor, group["group"]["name"], userID)
        group["group"]["users"] = groupContents["group"]["users"]
        group["group"]["chats"] = groupContents["group"]["chats"]
        group["accepted"] = groupContents["accepted"]
        group["writable"] = groupContents["writable"]
    print("GROUPS: ", groups)
    return groups
            

def getGroup(connection, cursor, groupName, userID):
    if cursor.execute("""SELECT g.readPrivate, g.writePrivate, gu.accepted, gu.writable FROM Groups g LEFT JOIN GroupsToUsers gu ON gu.groupName=g.name AND gu.userID=%s WHERE g.name=%s""", (userID, groupName)) > 0:
        row = cursor.fetchone()
        readPrivate = row[0]
        writePrivate = row[1]
        groupAccepted = row[2]
        groupWritable = row[3]
        if (not readPrivate or groupAccepted):
            group = {
                "name": groupName,
                "readPrivate": readPrivate,
                "writePrivate": writePrivate,
                "users": [],
                "chats": []
            }
            cursor.execute("""SELECT gu.userID, gu.accepted, gu.writable FROM GroupsToUsers gu WHERE gu.groupName=%s""", (groupName))
            userQueryRes = cursor.fetchall()
            for (userID, accepted, writable) in userQueryRes:
                print("USERID: ", userID)
                user = getUser(cursor, userID)
                print("USER: ", user)
                user["accepted"] = accepted
                user["writable"] = writable
                group["users"].append(user)
            cursor.execute("""SELECT c.id, c.name, c.subject FROM Chats c WHERE c.groupName=%s""", (groupName))
            for (chatID, chatName, chatSubject) in cursor:
                group["chats"].append({ "id": chatID, "name": chatName, "subject": chatSubject })
            return { "accepted": groupAccepted, "writable": groupWritable, "group": group }
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
            print("Message loop")
            for (id, text, objKey, creationEpochSecs, senderID) in cursor:
                print("Message: ", id)
                senderIDs[senderID] = True
                messages.append({ "id": id, "text": text, "objKey": objKey, "creationEpochSecs": creationEpochSecs, "chatID": chatID, "senderID": senderID })
            print("Senders loop")
            senders = []
            for senderID in senderIDs:
                print("Sender: ", senderID)
                senders.append(getUser(cursor, senderID))
            print("MS: ", messages, " SS", senders)
            return { "messages": messages, "senders": senders }
        return { "errMsg": "user does not have access" }
    return { "errMsg": "User not in group" }
    
    
def searchGroups(connection, cursor, query, userID):
    resp = []
    if cursor.execute("""SELECT g.name, g.readPrivate, g.writePrivate FROM Groups g
        WHERE LCASE(g.name) LIKE %s ORDER BY LENGTH(g.name), g.name LIMIT 50""", (query + '%')) > 0:
            for (name, readPrivate, writePrivate) in cursor:
                resp.append({"name": name, "readPrivate": readPrivate, "writePrivate": writePrivate})
    return resp
    
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
    return { "errMsg": "Event not found" }