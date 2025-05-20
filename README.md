# TripMate - Your Smart Travel Companion
TripMate is a smart travel planning app that leverages Neo4j for highly connected data like user relationships, travel itineraries, and collaborative planning. It enables users to book packages, plan trips, track budgets, chat with group members, and manage everything from a single platform

## Features
User Management
![WhatsApp Image 2025-05-18 at 18 31 16_db5175c6](https://github.com/user-attachments/assets/a9102134-25e8-4a0b-b4f1-31247aebd0fd)

Login / Signup 
![WhatsApp Image 2025-05-18 at 22 05 58_5d104940](https://github.com/user-attachments/assets/949c63b8-8d7a-4c50-9c63-68c135e797aa)

View Profile/Edit Profile – Manage user details and preferences
![WhatsApp Image 2025-05-20 at 10 57 21_3478a820](https://github.com/user-attachments/assets/4578f04f-c7d2-457c-9a7c-32a1e6c9b117)

## Trip Planning
Book Packages – Browse and reserve curated travel packages
![WhatsApp Image 2025-05-18 at 22 05 06_8b52ba98](https://github.com/user-attachments/assets/a9f2e176-8aee-4671-ae0d-92878eaa39d3)

Plan Itinerary – dynamic trip planning and optimization
![WhatsApp Image 2025-05-20 at 10 54 26_c7ff3ff9](https://github.com/user-attachments/assets/c5e98261-5c41-4ae4-95e0-d527f2e128be)

Budget Tracking – Track expenses and manage group budgets
![WhatsApp Image 2025-05-20 at 10 54 52_96df746e](https://github.com/user-attachments/assets/1e571f67-3fd5-4105-9525-f8cb527b22c0)


## Communication
Group Chat – Real-time messaging with fellow travelers
![WhatsApp Image 2025-05-20 at 10 54 08_40388482](https://github.com/user-attachments/assets/4c966912-9e1f-41e6-8638-2f5a09ce4f67)

Contact Us – Submit inquiries and support requests
![WhatsApp Image 2025-05-20 at 10 55 39_52addea4](https://github.com/user-attachments/assets/cb6cd92b-0068-4001-8463-071382e0cda4)


## Admin Features
Admin Dashboard – Access  package management, 
![WhatsApp Image 2025-05-20 at 10 58 51_69469dd9](https://github.com/user-attachments/assets/d38e28b2-0579-4324-a49c-e2e96cc17d80)

Manage Users & Packages – View  packages and edit 
![WhatsApp Image 2025-05-18 at 22 07 03_f38d530c](https://github.com/user-attachments/assets/e38c74ff-6ef6-4518-90c6-e89437cdacf4)


## Why Neo4j?
Trip planning involves deeply connected data—users, destinations, packages, expenses, messages, etc. Neo4j provides:
Intuitive modeling of relationships (e.g., who is in which group, booked what, shared what)
Fast traversal for itinerary and group-related queries
Flexibility in evolving trip structures without rigid schemas

## Tech Stack
Frontend: Html / css,js

Database: Neo4j (via neo4j-driver)

Admin Panel: custom dashboard

## Sample Code Snippet (Neo4j Query)
// Get user itinerary
const result = await session.run(`
  MATCH (u:User {id: $userId})-[:PLANNED]->(t:Trip)
  RETURN t
, { userId });

##  Contributing
Fork the repo
Create a new feature branch
Commit your changes
Open a pull request

## Conclusion
TripMate is designed to make travel planning smarter, easier, and more collaborative. With a powerful Neo4j-backed backend, real-time features like group chat, and a user-friendly interface, it’s the ultimate companion for solo travelers and groups alike.
Whether you're booking a package, tracking your trip budget, or planning every stop on your itinerary, TripMate keeps everything connected—just like your journey should be.
We’re constantly improving, so feel free to contribute, share feedback, or get in touch. Happy travels!

## Contact
Email: support@tripmate.com
Facebook Page :tripmate
![WhatsApp Image 2025-05-20 at 11 27 42_9f8f0cd7](https://github.com/user-attachments/assets/77981aab-00ff-4317-b25d-88e46ada2f9a)

