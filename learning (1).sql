-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Dec 09, 2025 at 10:08 AM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.1.25

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `learning`
--

-- --------------------------------------------------------

--
-- Table structure for table `alembic_version`
--

CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `alembic_version`
--

INSERT INTO `alembic_version` (`version_num`) VALUES
('9012defg');

-- --------------------------------------------------------

--
-- Table structure for table `assets`
--

CREATE TABLE `assets` (
  `id` int(11) NOT NULL,
  `url` varchar(1024) NOT NULL,
  `uploader_id` int(11) DEFAULT NULL,
  `size` int(11) DEFAULT NULL,
  `mime_type` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `assets`
--

INSERT INTO `assets` (`id`, `url`, `uploader_id`, `size`, `mime_type`, `created_at`) VALUES
(4, '/uploads/test.png', NULL, 68, 'image/png', '2025-11-06 18:03:18'),
(5, '/uploads/f8fbb33ff57142029099202da302829e_plain.png', NULL, 68, 'image/png', '2025-11-06 18:12:56'),
(6, '/uploads/IMG20220228115358.jpg', NULL, 2071667, 'image/jpeg', '2025-11-06 18:14:18'),
(7, '/uploads/fb54daedc65049a49d7cc43252fba3fd_plain.png', NULL, 68, 'image/png', '2025-11-06 18:17:59'),
(9, '/uploads/jsflow.png', NULL, 68, 'image/png', '2025-11-06 18:21:21'),
(10, '/uploads/passport_size.png', NULL, 26146, 'image/png', '2025-11-06 18:22:24'),
(11, '/uploads/charan_1.jpg', NULL, 133243, 'image/jpeg', '2025-11-07 17:30:46'),
(12, '/uploads/functional_oriented_design_vs_OOD.jpeg', NULL, 120505, 'image/jpeg', '2025-11-17 10:29:59');

-- --------------------------------------------------------

--
-- Table structure for table `courses`
--

CREATE TABLE `courses` (
  `id` int(11) NOT NULL,
  `title` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `thumbnail_url` varchar(1024) DEFAULT NULL,
  `thumbnail_asset_id` int(11) DEFAULT NULL,
  `category` varchar(100) DEFAULT NULL,
  `class_name` varchar(50) DEFAULT NULL,
  `price` int(11) DEFAULT NULL,
  `published` tinyint(1) DEFAULT NULL,
  `featured` tinyint(1) DEFAULT NULL,
  `duration_weeks` int(11) DEFAULT NULL,
  `weekly_hours` int(11) DEFAULT NULL,
  `difficulty` enum('beginner','intermediate','advanced') DEFAULT NULL,
  `stream` varchar(50) DEFAULT NULL,
  `tags` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `courses`
--

INSERT INTO `courses` (`id`, `title`, `description`, `created_at`, `thumbnail_url`, `thumbnail_asset_id`, `category`, `class_name`, `price`, `published`, `featured`, `duration_weeks`, `weekly_hours`, `difficulty`, `stream`, `tags`) VALUES
(4, 'Html', 'Hyper text markup language', '2025-10-31 06:39:59', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(15, 'E2E', 'created by automated test', '2025-11-06 18:03:18', '/uploads/test.png', 4, NULL, 'TestClass', NULL, 0, 0, NULL, NULL, 'intermediate', NULL, NULL),
(18, 'gfhhy', 'ythyju', '2025-11-06 18:14:18', '/uploads/IMG20220228115358.jpg', 6, 'physics', '10', 677, 0, 0, NULL, NULL, NULL, NULL, NULL),
(22, 'JS Flow Course', 'created via simulated js flow', '2025-11-06 18:21:21', '/uploads/jsflow.png', 9, 'mathematics', '11', 2499, 1, 1, 10, 6, 'advanced', 'science', 'cbse,advanced'),
(23, 'Enumer', 'hgngfnh', '2025-11-06 18:22:24', '/uploads/passport_size.png', 10, 'chemistry', '11', 45, 1, 0, 34, 4, 'beginner', 'commerce', 'CBSE'),
(25, 'History', 'The history of INDIA', '2025-11-17 10:29:59', '/uploads/functional_oriented_design_vs_OOD.jpeg', 12, 'social Sciences', '10', NULL, 1, 0, 12, 4, 'beginner', NULL, 'CBSE,Mathematics');

-- --------------------------------------------------------

--
-- Table structure for table `leaderboard`
--

CREATE TABLE `leaderboard` (
  `id` int(11) NOT NULL,
  `name` varchar(255) DEFAULT NULL,
  `rank` int(11) NOT NULL,
  `score` float DEFAULT NULL,
  `last_updated_date` datetime DEFAULT current_timestamp(),
  `league` enum('bronze','silver','gold','platinum') DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `leaderboard`
--

INSERT INTO `leaderboard` (`id`, `name`, `rank`, `score`, `last_updated_date`, `league`) VALUES
(1, 'Aayush', 1, 980, '2025-12-04 10:42:16', 'platinum'),
(2, 'Mahesh', 2, 870, '2025-12-04 10:42:16', 'gold'),
(3, 'Sachin', 3, 600, '2025-12-04 10:42:16', 'silver'),
(4, 'Parth Goel', 4, 230, '2025-12-09 14:21:13', NULL),
(5, 'Subhash Roy', 5, 100, '2025-12-09 14:22:13', NULL),
(6, 'Narasimha', 6, 60, '2025-12-09 14:28:42', NULL);

-- --------------------------------------------------------

--
-- Table structure for table `lessons`
--

CREATE TABLE `lessons` (
  `id` int(11) NOT NULL,
  `course_id` int(11) NOT NULL,
  `title` varchar(255) NOT NULL,
  `content_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`content_json`)),
  `content_version` int(11) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL,
  `description` text DEFAULT NULL,
  `duration` int(11) DEFAULT NULL,
  `level` varchar(50) DEFAULT NULL,
  `objectives` text DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `lessons`
--

INSERT INTO `lessons` (`id`, `course_id`, `title`, `content_json`, `content_version`, `created_at`, `description`, `duration`, `level`, `objectives`) VALUES
(6, 4, 'Images in html', '{\"description\": \"nfnfdvdf\", \"duration\": 45, \"level\": \"intermediate\", \"objectives\": \"bfhf\"}', 1, '2025-11-07 17:03:22', 'nfnfdvdf', 45, 'intermediate', 'bfhf'),
(8, 15, 'geometry', '{\"description\": \"ertertr\", \"duration\": 34, \"level\": \"intermediate\", \"objectives\": \"dtrrty tyh\"}', 1, '2025-11-07 17:27:32', 'ertertr', 34, 'intermediate', 'dtrrty tyh'),
(9, 4, 'Frames in html', '{\"description\": \"Discussing about the frames in html\", \"duration\": 20, \"level\": \"intermediate\", \"objectives\": \"The student can learn abt the frames in html\"}', 1, '2025-11-11 13:38:38', 'Discussing about the frames in html', 20, 'intermediate', 'The student can learn abt the frames in html'),
(10, 22, 'Edusaint js classes', '{\"description\": \"JS by edusaint\", \"duration\": 34, \"level\": \"intermediate\", \"objectives\": \"Learning js\"}', 1, '2025-11-17 10:02:30', 'JS by edusaint', 34, 'intermediate', 'Learning js');

-- --------------------------------------------------------

--
-- Table structure for table `notifications`
--

CREATE TABLE `notifications` (
  `id` int(11) NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `title` varchar(255) NOT NULL,
  `body` text DEFAULT NULL,
  `data` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`data`)),
  `is_read` tinyint(1) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `progress`
--

CREATE TABLE `progress` (
  `id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL,
  `lesson_id` int(11) NOT NULL,
  `score` float DEFAULT NULL,
  `time_spent` int(11) DEFAULT NULL,
  `answers` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`answers`)),
  `attempt_id` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `students`
--

CREATE TABLE `students` (
  `id` int(11) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password` char(6) NOT NULL,
  `syllabus` varchar(20) NOT NULL,
  `class` char(4) NOT NULL,
  `subjects` varchar(255) NOT NULL,
  `second_language` varchar(30) NOT NULL,
  `third_language` varchar(30) NOT NULL,
  `name` varchar(100) NOT NULL,
  `date` date DEFAULT NULL,
  `image` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `students`
--

INSERT INTO `students` (`id`, `email`, `password`, `syllabus`, `class`, `subjects`, `second_language`, `third_language`, `name`, `date`, `image`) VALUES
(2, 'aayush@gmail.com', 'pass12', 'ICSE', '9th', 'English,General Knowledge', 'Hindi', 'Tamil', 'Aayush', '2025-12-02', NULL),
(4, 'mahesh@gmail.com', 'pass14', 'CBSE', '8th', 'Social Science,Science', 'Hindi', 'Tamil', 'Mahesh', '2025-12-06', NULL),
(6, 'narasimha@gmail.com', 'pass16', 'ICSE', '8th', 'Science,Mathematics', 'Hindi', 'Sanskrit', 'Narasimha', '2025-12-09', NULL),
(3, 'parth@gmail.com', 'pass13', 'State Board', '10th', 'Social Science,Computer Science', 'Hindi', 'Tamil', 'Parth Goel', '2025-12-01', NULL),
(1, 'sachin.patro@edusaint.in', 'pass11', 'CBSE', '8th', 'Science,Mathematics', 'Hindi', 'Sanskrit', 'Sachin', '2025-12-04', NULL),
(5, 'subhash@gmail.com', 'pass15', 'ICSE', '9th', 'Social Science,Science', 'Hindi', 'Tamil', 'Subhash Roy', '2025-12-08', NULL);

-- --------------------------------------------------------

--
-- Table structure for table `topics`
--

CREATE TABLE `topics` (
  `id` int(11) NOT NULL,
  `lesson_id` int(11) NOT NULL,
  `title` varchar(255) DEFAULT NULL,
  `data_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`data_json`)),
  `created_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `topics`
--

INSERT INTO `topics` (`id`, `lesson_id`, `title`, `data_json`, `created_at`) VALUES
(11, 9, 'Prefab', '{\"description\": \"fdgrh\", \"objectives\": [\"fgd\"], \"cards\": []}', '2025-11-14 13:39:04'),
(12, 9, 'Horizonal', '{\"description\": \"gbgf\", \"objectives\": [], \"cards\": []}', '2025-11-14 13:44:29'),
(17, 10, 'Arrays in JS', '{\"description\": \"Arrays\", \"estimated_time\": 4, \"difficulty\": \"easy\", \"order\": 1, \"objectives\": [], \"cardTypes\": [], \"category\": \"mathematics\", \"course_id\": \"22\"}', '2025-11-17 10:03:18'),
(18, 8, 'Circles and lines', '{\"description\": \"Circles ing geometry\", \"estimated_time\": 23, \"difficulty\": \"medium\", \"order\": 1, \"objectives\": [\"Define reflection and the law of r\", \"Identify incident ray, reflected ray\", \"Differentiate between specular an\"], \"cardTypes\": [], \"category\": null, \"course_id\": \"15\"}', '2025-11-17 10:11:10');

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `id` int(11) NOT NULL,
  `email` varchar(255) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` enum('student','teacher','admin') NOT NULL,
  `created_at` datetime DEFAULT NULL,
  `name` varchar(500) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`id`, `email`, `password_hash`, `role`, `created_at`, `name`) VALUES
(15, 'n210163@rguktn.ac.in', 'scrypt:32768:8:1$N3KaQKwfIM2zHS84$a5d77ee3c146bbe2f55b2f6bfc1ffb668610fbd882db8877e3c160d7569d2d60006c4c7e38a5f9b17b1fcd8eb6fd1a4e0e958d6127bc9d98bab31c8c687cf1a9', 'admin', '2025-10-29 18:43:14', 'Naga Mahesh Kona'),
(21, 'sachin.patro@gmail.com', 'scrypt:32768:8:1$TtA72l0ZaBd2XxIV$4ec12a7581ada2c2e6c4dfb041e287f99ab58ce5ee713d6fd09c20489bd6dca3864ca48d98ea470e39a0f1896334341cced2c484104b14f8c4bde6c8647d0b90', 'admin', '2025-11-17 10:54:58', ''),
(23, 'testapi@example.com', 'scrypt:32768:8:1$V9DjzL4fo9RS5QlT$26988d3fb4831fe794d4aa32c7d532c20828323283ae53f002bdf4bac6390b33544a07f32e9141b20c1e53b59695e61d918492548fc46be49561881d2235a04e', 'student', '2025-12-09 05:47:09', '');

--
-- Indexes for dumped tables
--

--
-- Indexes for table `alembic_version`
--
ALTER TABLE `alembic_version`
  ADD PRIMARY KEY (`version_num`);

--
-- Indexes for table `assets`
--
ALTER TABLE `assets`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_assets_created_at` (`created_at`),
  ADD KEY `ix_assets_uploader_id` (`uploader_id`);

--
-- Indexes for table `courses`
--
ALTER TABLE `courses`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_courses_created_at` (`created_at`),
  ADD KEY `ix_courses_title` (`title`),
  ADD KEY `ix_courses_category` (`category`),
  ADD KEY `ix_courses_class_name` (`class_name`),
  ADD KEY `ix_courses_difficulty` (`difficulty`),
  ADD KEY `fk_courses_thumbnail_asset` (`thumbnail_asset_id`),
  ADD KEY `ix_courses_published` (`published`);

--
-- Indexes for table `leaderboard`
--
ALTER TABLE `leaderboard`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_leaderboard_rank` (`rank`);

--
-- Indexes for table `lessons`
--
ALTER TABLE `lessons`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_lessons_course_id` (`course_id`),
  ADD KEY `ix_lessons_created_at` (`created_at`),
  ADD KEY `ix_lessons_title` (`title`);

--
-- Indexes for table `notifications`
--
ALTER TABLE `notifications`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_notifications_created_at` (`created_at`),
  ADD KEY `ix_notifications_is_read` (`is_read`),
  ADD KEY `ix_notifications_user_id` (`user_id`);

--
-- Indexes for table `progress`
--
ALTER TABLE `progress`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_progress_attempt_id` (`attempt_id`),
  ADD KEY `ix_progress_attempt_id` (`attempt_id`),
  ADD KEY `ix_progress_created_at` (`created_at`),
  ADD KEY `ix_progress_lesson_id` (`lesson_id`),
  ADD KEY `ix_progress_user_id` (`user_id`),
  ADD KEY `ix_progress_user_lesson` (`user_id`,`lesson_id`);

--
-- Indexes for table `students`
--
ALTER TABLE `students`
  ADD PRIMARY KEY (`email`),
  ADD UNIQUE KEY `id` (`id`),
  ADD UNIQUE KEY `unique_students_email` (`email`);

--
-- Indexes for table `topics`
--
ALTER TABLE `topics`
  ADD PRIMARY KEY (`id`),
  ADD KEY `ix_topics_created_at` (`created_at`),
  ADD KEY `ix_topics_lesson_id` (`lesson_id`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `ix_users_email` (`email`),
  ADD KEY `ix_users_created_at` (`created_at`),
  ADD KEY `ix_users_role` (`role`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `assets`
--
ALTER TABLE `assets`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=13;

--
-- AUTO_INCREMENT for table `courses`
--
ALTER TABLE `courses`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=26;

--
-- AUTO_INCREMENT for table `leaderboard`
--
ALTER TABLE `leaderboard`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=7;

--
-- AUTO_INCREMENT for table `lessons`
--
ALTER TABLE `lessons`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=11;

--
-- AUTO_INCREMENT for table `notifications`
--
ALTER TABLE `notifications`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `progress`
--
ALTER TABLE `progress`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=3;

--
-- AUTO_INCREMENT for table `students`
--
ALTER TABLE `students`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=8;

--
-- AUTO_INCREMENT for table `topics`
--
ALTER TABLE `topics`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=19;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=24;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `assets`
--
ALTER TABLE `assets`
  ADD CONSTRAINT `assets_ibfk_1` FOREIGN KEY (`uploader_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `courses`
--
ALTER TABLE `courses`
  ADD CONSTRAINT `fk_courses_thumbnail_asset` FOREIGN KEY (`thumbnail_asset_id`) REFERENCES `assets` (`id`);

--
-- Constraints for table `lessons`
--
ALTER TABLE `lessons`
  ADD CONSTRAINT `lessons_ibfk_1` FOREIGN KEY (`course_id`) REFERENCES `courses` (`id`);

--
-- Constraints for table `notifications`
--
ALTER TABLE `notifications`
  ADD CONSTRAINT `notifications_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `progress`
--
ALTER TABLE `progress`
  ADD CONSTRAINT `progress_ibfk_1` FOREIGN KEY (`lesson_id`) REFERENCES `lessons` (`id`),
  ADD CONSTRAINT `progress_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`);

--
-- Constraints for table `topics`
--
ALTER TABLE `topics`
  ADD CONSTRAINT `topics_ibfk_1` FOREIGN KEY (`lesson_id`) REFERENCES `lessons` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
