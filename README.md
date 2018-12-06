# SyllaShare Lambda

Serverless functions for SyllaShare invoked by AWS AppSync & API Gateway.  Most endpoints are Python but some are written in Node.js.

## Endpoints
### Mutations
| Method  | Description |
| ------------- | ------------- |
| CreateGroup  | Current user creates and joins a group from a group name and access settings  |
| JoinGroup  | Current user joins a specified group |
| LeaveGroup | Current user or specified user is removed from a group |
| InviteToGroup | Send invite to user to a group |
| CreateChat | Create a chat for a group |
| CreateMessage | Send message to other users in a chat |
| SetWritable | Upgrade or downgrade a user's permission to a group |
| CreateClass | Make a class from class section, teacher name, etc. and events |
| UpdateEvents | Update or create group calendar events |
| DeleteEvents | Delete group calendar events |

### Queries
| Method  | Description |
| ------------- | ------------- |
| GetGroups | Get groups for a user |
| GetMessages | Get messages for a chat |
| SearchGroups| Get groups whose names are close to a query |
| GetGroup | Get group from group name |
| SearchCourses | Get courses whose names or titles are close to query |
| GetClass | Get class data like class name, teacher, and group information |
| GetUserClasses | Get classes for specified user |
| SearchTeachers | Get teachers whose names are close to query |
| GetTerm | Get date ranges for a school's term |

## AppSync Definitions
```
type Mutation {
	createGroup(groupName: String!, readPrivate: Boolean!, writePrivate: Boolean!): MinGroup
	joinGroup(groupName: String!): GroupUserPair
	leaveGroup(groupName: String!, kickUserID: String): GroupUserPair
	inviteToGroup(groupName: String!, inviteToUserID: String!, write: Boolean!): GroupUserPair
	createChat(groupName: String!, chatName: String!, chatSubject: String): Chat
	createMessage(
		chatID: String!,
		text: String,
		objKey: String,
		creationEpochSecs: Int
	): MessageSenderPair
	setWritable(groupName: String!, setUserID: String!, writable: Boolean!): UserWritablePair
	createClass(
		courseID: String!,
		schoolName: String!,
		term: String!,
		year: Int!,
		courseName: String,
		teacherName: String,
		timeStr: String,
		writePrivate: Boolean
	): Class
	updateEvents(groupName: String, events: [EventInput], personal: Boolean): Events
	deleteEvents(groupName: String, eventIDs: [String], personal: Boolean): Events
}

type Query {
	getGroups: [GroupWithStatus]
	getGroup(groupName: String!): GroupWithStatus
	getMessages(chatID: String!): ChatContents
	searchGroups(query: String!): [MinGroup]
	searchCourses(query: String!): [Course]
	getClasses(courseID: String!): [Class]
	getClass(classID: String!): Class
	getUserClasses(userID: String!): [Class]
	getUserEvents(userID: String!): [Event]
	searchTeachers(query: String!): [Teacher]
	getTerm(schoolName: String!, year: String!, term: String!): Term
}

type Subscription {
	subJoinGroup(groupName: String!): GroupUserPair
		@aws_subscribe(mutations: ["joinGroup"])
	subLeaveGroup(groupName: String!): GroupUserPair
		@aws_subscribe(mutations: ["leaveGroup"])
	subInviteToGroup(groupName: String!): GroupUserPair
		@aws_subscribe(mutations: ["inviteToGroup"])
	subUserInviteToGroup(userID: String!): GroupUserPair
		@aws_subscribe(mutations: ["inviteToGroup"])
	subCreateChat(groupName: String!): Chat
		@aws_subscribe(mutations: ["createChat"])
	subCreateMessage(chatID: String!): MessageSenderPair
		@aws_subscribe(mutations: ["createMessage"])
	subEventsUpdated(groupName: String!): Events
		@aws_subscribe(mutations: ["updateEvents"])
	subEventsDeleted(groupName: String!): Events
		@aws_subscribe(mutations: ["deleteEvents"])
}

type Chat {
	id: String!
	name: String!
	subject: String
	groupName: String
}

type ChatContents {
	messages: [Message]
	senders: [User]
}

type Class {
	id: String!
	course: Course
	teacher: Teacher
	term: String
	year: Int
	timeStr: String
	group: GroupWithStatus
}

type Course {
	id: String!
	name: String
	school: School
}

type Event {
	id: String!
	name: String
	time: String
	mins: Int
	priority: Int
	groupName: String
	classID: String
}

input EventInput {
	name: String!
	time: String!
	mins: Int
	priority: Int
	id: String
}

type Events {
	events: [Event]
	groupName: String
}

type Group {
	name: String!
	readPrivate: Boolean!
	writePrivate: Boolean!
	users: [User]
	chats: [Chat]
	events: [Event]
	courseID: String
}

type GroupUserPair {
	userID: String!
	groupName: String!
	group: Group
	user: User
}

type GroupWithStatus {
	accepted: Boolean
	writable: Boolean
	group: Group
}

type Message {
	id: String!
	text: String
	objKey: String
	creationEpochSecs: Int
	chatID: String
	senderID: String
}

type MessageSenderPair {
	chatID: String!
	message: Message
	sender: User
}

type MinGroup {
	name: String!
	readPrivate: Boolean
	writePrivate: Boolean
}

type School {
	name: String!
	city: String
	state: String
	picKey: String!
}

type Teacher {
	name: String!
	school: School
}

type Term {
	start: String
	end: String
}

type User {
	id: String!
	username: String!
	firstName: String
	lastName: String
	picKey: String
	school: School
	accepted: Boolean
	writable: Boolean
}

type UserWritablePair {
	userID: String
	writable: Boolean
}
```
