// init-mongo.js
// creation des utilisateurs au premier demarrage du conteneur

db = db.getSiblingDB(process.env.MONGO_DB || "healthcare");

// user applicatif (utilisé par loader.py)
db.createUser({
  user: process.env.APP_USER || "appuser",
  pwd: process.env.APP_PASSWORD || "appsecret",
  roles: [
    { role: "readWrite", db: process.env.MONGO_DB || "healthcare" }
  ]
});

// user lecture seule (pour le reporting)
db.createUser({
  user: process.env.READONLY_USER || "readOnlyUser",
  pwd: process.env.READONLY_PASSWORD || "lectureseule",
  roles: [
    { role: "read", db: process.env.MONGO_DB || "healthcare" }
  ]
});

// user support : peut gerer les index et collections en plus du CRUD
db.createUser({
  user: process.env.SUPPORT_USER || "supportUser",
  pwd: process.env.SUPPORT_PASSWORD || "supportpassword",
  roles: [
    { role: "read", db: process.env.MONGO_DB || "healthcare" },
    { role: "readWrite", db: process.env.MONGO_DB || "healthcare" },
    { role: "dbAdmin", db: process.env.MONGO_DB || "healthcare" }
  ]
});

// admin avancé : supervision + cluster
db.createUser({
  user: process.env.ADMIN_USER || "adminUser",
  pwd: process.env.ADMIN_PASSWORD || "adminpassword",
  roles: [
    { role: "readWrite", db: process.env.MONGO_DB || "healthcare" },
    { role: "dbAdmin", db: process.env.MONGO_DB || "healthcare" },
    { role: "clusterAdmin", db: "admin" }
  ]
});
