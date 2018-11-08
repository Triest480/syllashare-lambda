import pymysql
import json
import os
import uuid
import time

def getUser(cursor, userID):
    cursor.execute("""SELECT u.id AS id, u.username AS username, u.first_name AS firstName, u.last_name AS lastName, u.pic_key AS picKey, 
        s.name AS schoolName, s.city AS schoolCity, s.state AS schoolState, s.pic_key AS schoolPicKey
        FROM user_data_school u LEFT JOIN user_data_school s ON u.school_id=s.name
        WHERE u.id=?""", (userID))
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
    
    
def isInGroup(cursor, groupName, userID):
    return (cursor.execute('SELECT groupName FROM GroupsToUsers WHERE groupName=? AND userID=?', (groupName, userID)) > 0)
    
    
def createGroup(connection, cursor, groupName, groupPrivate, userID):
    if cursor.execute('INSERT INTO Groups VALUES (?, ?)', (groupName, groupPrivate)) > 0:
        if cursor.execute('INSERT INTO GroupsToUsers VALUES (?, ?, ?)', (groupName, userID, True)) > 0:
            connection.commit()
            return { "name": groupName, "private": groupPrivate }
        return { "errMsg": "Failed to add user into group" }
    return { "errMsg": "Failed to create group" }
    
    
def joinGroup(connection, cursor, groupName, userID):
    if cursor.execute('SELECT private FROM Groups WHERE name=?', (groupName)) > 0:
        groupPrivate = cursor.fetchone()[0]
        if groupPrivate:
            if cursor.execute('UPDATE GroupsToUsers SET accepted=? WHERE groupName=? AND userID=? ', (True, groupName, userID)) <= 0:
                return { "errMsg": "User not invited" }
        else:
            cursor.execute('INSERT INTO GroupToUsers VALUES (:1, :2, :3) ON DUPLICATE KEY UPDATE accepted=:3', (groupName, groupPrivate, True))
        connection.commit()
        return { "groupName": groupName, "user": getUser(cursor, userID) }
    return { "errMsg": "Group not found" }


def leaveGroup(connection, cursor, groupName, userID):
    if cursor.execute('DELETE FROM GroupToUsers WHERE groupName=? AND userID=?', (groupName, userID)) > 0:
        connection.commit()
        return { "groupName": groupName, "user": getUser(cursor, userID) }
    return { "errMsg": "Not in or have not been invited to group" }
    
    
def inviteToGroup(connection, cursor, groupName, inviteToUserID, invokerUserID):
    if isInGroup(cursor, groupName, invokerUserID):
        if cursor.execute('INSERT INTO GroupToUsers VALUES (?, ?, ?)', (groupName, inviteToUserID, False)) > 0:
            connection.commit()
            return { "groupName": groupName, "user": getUser(cursor, inviteToUserID) }
        return { "errMsg": "Failed to invite user" }
    return { "errMsg": "You can't invite someone to a group you're not in" }
    
    
def createChat(connection, cursor, groupName, chatName, chatSubject, userID):
    if isInGroup(cursor, groupName, userID):
        chatID = uuid.uuid4()
        if cursor.execute('INSERT INTO Chats VALUES (?, ?, ?, ?)', (chatID, groupName, chatName, chatSubject)) > 0:
            connection.commit()
            return { "id": chatID, "name": chatName, "subject": chatSubject }
        return { "errMsg": "Could not create group" }
    return { "errMsg": "User is not in group" }
  
    
def createMessage(connection, cursor, chatID, text, objKey, creationEpochSecs, userID):
    #Check if user is part of group that the chat belongs to
    if cursor.execute("""SELECT c.id FROM Chats c 
        INNER JOIN GroupsToUsers gu ON c.groupName=gu.groupName 
        WHERE c.id=? AND gu.userID=? AND gu.accepted=?""", (chatID, userID, True)) > 0:
            msgID = uuid.uuid4()
            if cursor.execute("""INSERT INTO Messages VALUES (?, ?, ?, ?, ?)""", (msgID, chatID, text, objKey, creationEpochSecs)) > 0:
                connection.commit()
                return { "msgID": msgID, "text": text, "objKey": objKey, "creationEpochSecs": creationEpochSecs }
            return { "errMsg": "Could not add message" }
    return { "errMsg": "User not in group" }
    
    
def getGroups(connection, cursor, userID):
    cursor.execute("""SELECT g.groupName, g.private FROM GroupsToUsers gu INNER JOIN Groups ON gu.groupName=g.name WHERE gu.userID=?""", (userID))
    groups = []
    for (groupName, groupPrivate) in cursor:
        groups.append({ "name": groupName, "private": groupPrivate })
    for group in groups:
        groupContents = getGroup(connection, cursor, group.name, userID)
        group["users"] = groupContents["users"]
        group["chats"] = groupContents["chats"]
    return groups
            

def getGroup(connection, cursor, groupName, userID):
    if cursor.execute("""SELECT g.private FROM GroupsToUsers gu INNER JOIN Groups ON gu.groupName=g.name WHERE gu.userID=? AND gu.groupName=?""", (userID, groupName)) > 0:
        groupPrivate = cursor.fetchone()[0]
        group = {
            "name": groupName,
            "private": groupPrivate
        }
        cursor.execute("""SELECT gu.userID FROM GroupsToUsers gu WHERE gu.userID!=? AND gu.groupName=?""", (userID, groupName))
        for (userID) in cursor:
            group["users"] = getUser(cursor, userID)
        cursor.execute("""SELECT c.id, c.name, c.subject FROM Chats c WHERE c.groupName=?""", (groupName))
        for (chatID, chatName, chatSubject) in cursor:
            group["chats"] = { "id": chatID, "name": chatName, "subject": chatSubject }
        return group
    return { "errMsg": "User not a member of group or group does not exist" }


def getMessages(connection, cursor, chatID, userID):
    if cursor.execute("""SELECT c.id FROM Chats c 
        INNER JOIN GroupsToUsers gu ON c.groupName=gu.groupName 
        WHERE c.id=? AND gu.userID=? AND gu.accepted=?""", (chatID, userID, True)) > 0:
            messages = []
            cursor.execute("""SELECT id, text, objKey, creationEpochSecs FROM Messages WHERE chatID=? ORDER BY creationEpochSecs""", (chatID))
            for (id, text, objKey, creationEpochSecs) in cursor:
                messages.append({ "id": id, "text": text, "objKey": objKey, "creationEpochSecs": creationEpochSecs })
            return messages
    return { "errMsg": "User not in group" }
    
    
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
    
    args = event.arguments
    #python has no switch-case
    if (event["type"] == "CreateGroup"):
        return createGroup(connection, cursor, args["groupName"], args["groupPrivate"], userID)
    elif (event["type"] == "JoinGroup"):
        return joinGroup(connection, cursor, args["groupName"], userID)
    elif (event["type"] == "LeaveGroup"):
        return leaveGroup(connection, cursor, args["groupName"], userID)
    elif (event["type"] == "InviteToGroup"):
        return inviteToGroup(connection, cursor, args["groupName"], args["inviteToUserID"], userID)
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
    return { "errMsg": "Event not found" }