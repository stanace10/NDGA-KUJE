# NDGA Portal

Notre Dame Girls' Academy, Kuje-Abuja runs on a custom multi-role school operations portal built for academic management, finance, CBT, elections, reporting, and student-family access.

This README is the main explanation document for the current portal build.

## What This System Is

The NDGA Portal is a school operations platform, not just a student login page.

It supports:
- student records and profiles
- staff and admin role-based access
- attendance
- result entry, review, approval, and publishing
- CBT authoring, activation, attempts, and marking
- finance records and payment visibility
- election management
- notifications and messaging
- learning-hub features for students and teachers
- backup, audit, and operational controls

## Who Uses It

- Students
- Parents and guardians
- Subject teachers
- Form teachers
- Deans
- Vice Principal
- Principal
- Bursar
- IT Manager

## Core Portal Modules

### 1. Student Portal
- profile and biodata view
- attendance visibility
- subject view
- result and transcript access
- payment visibility
- document vault
- learning hub
- weekly challenge
- digital ID card

### 2. Staff Portal
- staff profile
- lesson planner
- assigned academic workflows
- controlled access into results and CBT based on role

### 3. Results System
- teacher score entry
- dean review
- form-teacher compilation
- VP approval and publishing
- principal oversight and override path where allowed
- PDF report generation
- result comments and analytics support

### 4. CBT System
- question authoring
- upload/import
- AI-assisted draft support
- dean review
- IT activation
- objective auto-marking
- theory marking queue
- attempt integrity tracking

### 5. Finance System
- charges
- fees
- payments
- receipts
- debtors
- reminders
- student finance visibility
- bursar operations

### 6. Elections
- positions
- candidates
- voter scoping
- one-vote enforcement
- audit trail
- result analytics

### 7. Learning Hub
- published study materials
- assignments
- practice resources
- teacher lesson planner output
- student AI tutor
- weekly challenge activities

Important note:
This is not yet a full traditional LMS with course progression, assignment submission tracking, and classroom discussion threads. It currently includes a light LMS-style learning hub inside the broader portal.

## Architecture Decision

The portal now follows a LAN-first operating model.

### LAN
The school LAN is the main working environment for operational activity.

This is where core school work is done:
- result entry
- result approval workflows
- attendance
- CBT authoring and activation workflows
- elections
- bursar operational work
- IT provisioning and school setup work
- image uploads and core records work

### Cloud
The cloud is now mainly for visibility and external access.

Cloud remains important for:
- student and parent login from outside school
- viewing results
- downloading reports
- fee payment visibility and payment flow
- selected profile/settings access
- limited communication and external-facing access where needed

### Why This Decision Was Made

The LAN-first model was chosen to reduce:
- missing scores after backups or mixed updates
- instability from weak internet during school operations
- conflicting records between LAN and cloud
- risk around high-stakes academic data

It also improves:
- reliability of school-day operations
- control of student data
- confidence in backups
- recovery readiness if cloud services fail

## Data Movement Model

The portal no longer uses normal automatic web-app sync as an everyday workflow.

Current model:
- work is done on LAN
- cloud serves external viewing and access needs
- updates from LAN to cloud are pushed manually by IT when required
- cloud-to-LAN pulls can still be done where operationally necessary

This means:
- the school database on LAN is treated as the primary operational source
- cloud can be refreshed on a daily, weekly, or controlled schedule
- if cloud fails, LAN still holds the live working record base

## Role Summary

### IT Manager
- controls setup, users, assignments, features, operational access, and infrastructure-facing workflows

### Subject Teacher
- enters scores only for assigned class-subject windows
- authors CBT content for assigned teaching windows
- uses lesson planner and learning resources

### Form Teacher
- manages class attendance
- compiles class results after subject approval flow is complete

### Dean
- reviews teacher result sheets
- reviews CBT drafts before IT activation

### Vice Principal
- reviews compiled class result workflows
- approves or rejects publishing flow

### Principal
- oversight access
- result publication oversight
- official settings and leadership visibility

### Bursar
- finance operations
- payment records
- receipts and debt tracking

### Student
- learning, profile, finance, result, and document access

## Main Workflows

### Results
1. Teacher enters scores.
2. Dean reviews.
3. Form teacher compiles.
4. VP approves or rejects.
5. Principal retains oversight.
6. Published reports become visible to students and families.

### CBT
1. Teacher creates draft.
2. Dean reviews.
3. IT activates.
4. Students take exam.
5. Objective scores mark automatically.
6. Theory work is reviewed where required.
7. Results can feed academic records.

### Attendance
1. Form teacher records attendance on LAN.
2. Attendance becomes part of reporting and student visibility.

### Finance
1. Bursar manages charges and payment records on LAN.
2. Student and parent-facing finance visibility remains available through cloud access as updated.

## Technical Shape

- Django-based application
- role-based multi-portal structure
- PostgreSQL data layer
- Redis/Celery support
- media/file handling
- audit and integrity support
- Docker-based deployment setup for LAN and cloud environments

Main app areas:
- `apps/accounts`
- `apps/academics`
- `apps/attendance`
- `apps/cbt`
- `apps/dashboard`
- `apps/finance`
- `apps/results`
- `apps/elections`
- `apps/notifications`
- `apps/setup_wizard`
- `apps/sync`

## Current Public-Site Status

The old public website layer was removed.

The next public website will be rebuilt separately from scratch. This repository currently reflects the portal product and backend school operations platform.

## Operations Notes

- LAN is the working authority for school operations.
- Cloud is mainly for access, visibility, and controlled external use.
- Manual push is the intended update path.
- Backup and restore discipline remains important.
- High-stakes work should not depend on unstable internet.

## Recommended Supporting Docs

- `docs/OPS_RUNTIME_AND_RESTORE_DRILLS.md`
- `docs/MOBILE_WORKFLOW_ACCEPTANCE.md`

## Short Summary For Non-Technical Readers

NDGA Portal is a custom-built school management system for Notre Dame Girls' Academy, Kuje-Abuja. It handles academics, results, attendance, CBT, finance, elections, student access, and selected learning support. The school now operates it primarily from the LAN for reliability and data safety, while the cloud side remains available for student and parent visibility, payments, and controlled external access.
