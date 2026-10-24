package main

import (
        "encoding/json"
        "log"
        "net/http"
        "strings"

        "github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
        CheckOrigin: func(r *http.Request) bool {
                return true
        },
}

type Message struct {
        Type     string   `json:"type"`
        Text     string   `json:"text"`
        Services []string `json:"services,omitempty"`
        Options  []string `json:"options,omitempty"`
}

type IncomingMessage struct {
        Text string `json:"text"`
}

type Session struct {
        Stage         string
        Service       string
        Issue         string
        ErrorMessage  string
        Environment   string
        RecentChanges string
        Scope         string
}

var services = []string{
        "audio-cutter",
        "audio-joiner",
        "audio-to-video",
        "image-compressor",
        "image-to-pdf",
        "pdf-to-jpg",
        "pdf-to-word",
        "video-cutter",
        "video-subtitle",
        "video-to-gif",
        "video-to-reels",
        "word-to-pdf",
        "gateway",
        "payment",
        "user-service",
}

var serviceNames = map[string]string{
        "audio-cutter":     "Audio Cutter",
        "audio-joiner":     "Audio Joiner",
        "audio-to-video":   "Audio to Video",
        "image-compressor": "Image Compressor",
        "image-to-pdf":     "Image to PDF",
        "pdf-to-jpg":       "PDF to JPG",
        "pdf-to-word":      "PDF to Word",
        "video-cutter":     "Video Cutter",
        "video-subtitle":   "Video Subtitle",
        "video-to-gif":     "Video to GIF",
        "video-to-reels":   "Video to Reels",
        "word-to-pdf":      "Word to PDF",
        "gateway":          "Gateway",
        "payment":          "Payment",
        "user-service":     "User Service",
}

func main() {
        mux := http.NewServeMux()

        mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
                w.Header().Set("Content-Type", "application/json")
                w.WriteHeader(http.StatusOK)
                _, _ = w.Write([]byte(`{"status":"ok"}`))
        })

        mux.HandleFunc("/ws", ws)

        staticFiles := http.FileServer(http.Dir("./static"))
        mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
                if r.URL.Path == "/" {
                        http.ServeFile(w, r, "./static/index.html")
                        return
                }
                staticFiles.ServeHTTP(w, r)
        })

        log.Println("Support Bot Alina listening on :5017")
        log.Fatal(http.ListenAndServe(":5017", mux))
}

func normalize(value string) string {
        return strings.ToLower(strings.TrimSpace(value))
}

func send(conn *websocket.Conn, message Message) error {
        return conn.WriteJSON(message)
}

func sendText(conn *websocket.Conn, text string) error {
        return send(conn, Message{
                Type: "message",
                Text: text,
        })
}

func sendOptions(conn *websocket.Conn, text string, options []string) error {
        return send(conn, Message{
                Type:    "options",
                Text:    text,
                Options: options,
        })
}

func sendServices(conn *websocket.Conn, text string) error {
        return send(conn, Message{
                Type:     "services",
                Text:     text,
                Services: services,
        })
}

func receiveText(raw []byte) string {
        text := strings.TrimSpace(string(raw))

        var incoming IncomingMessage
        if json.Unmarshal(raw, &incoming) == nil &&
                strings.TrimSpace(incoming.Text) != "" {
                text = strings.TrimSpace(incoming.Text)
        }

        return text
}

func findService(value string) string {
        query := normalize(value)

        for _, service := range services {
                if query == service || strings.Contains(query, service) {
                        return service
                }
        }

        aliases := []struct {
                alias   string
                service string
        }{
                {"audio cutter", "audio-cutter"},
                {"cut audio", "audio-cutter"},
                {"audio cutting", "audio-cutter"},
                {"audio joiner", "audio-joiner"},
                {"join audio", "audio-joiner"},
                {"merge audio", "audio-joiner"},
                {"audio to video", "audio-to-video"},
                {"image compressor", "image-compressor"},
                {"compress image", "image-compressor"},
                {"image compression", "image-compressor"},
                {"image to pdf", "image-to-pdf"},
                {"pdf to jpg", "pdf-to-jpg"},
                {"pdf to word", "pdf-to-word"},
                {"video cutter", "video-cutter"},
                {"cut video", "video-cutter"},
                {"video cutting", "video-cutter"},
                {"video subtitle", "video-subtitle"},
                {"subtitles", "video-subtitle"},
                {"video to gif", "video-to-gif"},
                {"video to reels", "video-to-reels"},
                {"word to pdf", "word-to-pdf"},
                {"gateway", "gateway"},
                {"website", "gateway"},
                {"home page", "gateway"},
                {"payment", "payment"},
                {"checkout", "payment"},
                {"transaction", "payment"},
                {"user service", "user-service"},
                {"login", "user-service"},
                {"registration", "user-service"},
                {"register", "user-service"},
                {"account", "user-service"},
        }

        for _, item := range aliases {
                if strings.Contains(query, item.alias) {
                        return item.service
                }
        }

        return ""
}

func isYes(value string) bool {
        query := normalize(value)

        switch query {
        case "yes", "y", "yeah", "yep", "yes please",
                "resolved", "fixed", "working now", "issue resolved",
                "yes, resolved", "yes resolved":
                return true
        }

        return strings.HasPrefix(query, "yes ")
}

func isNo(value string) bool {
        query := normalize(value)

        switch query {
        case "no", "n", "nope", "no thanks", "not resolved",
                "still failing", "still broken", "still not working",
                "not fixed", "no, still happening":
                return true
        }

        return strings.HasPrefix(query, "no ")
}

func questionForService(service string) string {
        switch service {
        case "audio-cutter":
                return "What problem are you experiencing with Audio Cutter?"
        case "audio-joiner":
                return "What problem are you experiencing with Audio Joiner?"
        case "audio-to-video":
                return "What problem are you experiencing with Audio to Video?"
        case "image-compressor":
                return "What problem are you experiencing with Image Compressor?"
        case "image-to-pdf":
                return "What problem are you experiencing with Image to PDF?"
        case "pdf-to-jpg":
                return "What problem are you experiencing with PDF to JPG?"
        case "pdf-to-word":
                return "What problem are you experiencing with PDF to Word?"
        case "video-cutter":
                return "What problem are you experiencing with Video Cutter?"
        case "video-subtitle":
                return "What problem are you experiencing with Video Subtitle?"
        case "video-to-gif":
                return "What problem are you experiencing with Video to GIF?"
        case "video-to-reels":
                return "What problem are you experiencing with Video to Reels?"
        case "word-to-pdf":
                return "What problem are you experiencing with Word to PDF?"
        case "gateway":
                return "What problem are you experiencing with the website or gateway?"
        case "payment":
                return "What problem are you experiencing with payment?"
        case "user-service":
                return "What problem are you experiencing with login, registration, or your account?"
        default:
                return "Please describe the problem you are experiencing."
        }
}

func issueOptions(service string) []string {
        switch service {
        case "audio-cutter", "video-cutter":
                return []string{"Upload fails", "Invalid start or end time", "Processing fails", "Output file is missing", "Other error"}
        case "audio-joiner":
                return []string{"Upload fails", "Files will not join", "Output is incomplete", "Audio quality problem", "Other error"}
        case "audio-to-video":
                return []string{"Upload fails", "Conversion fails", "Background image problem", "Output video has no audio", "Other error"}
        case "image-compressor":
                return []string{"Upload fails", "Compression fails", "Image quality is poor", "Output is missing", "Other error"}
        case "image-to-pdf":
                return []string{"Upload fails", "Conversion fails", "Some images are missing", "PDF layout is incorrect", "Other error"}
        case "pdf-to-jpg":
                return []string{"PDF upload fails", "Conversion fails", "Some pages are missing", "JPG output is missing", "Other error"}
        case "pdf-to-word", "word-to-pdf":
                return []string{"Upload fails", "Conversion fails", "Formatting is incorrect", "Output file is missing", "Other error"}
        case "video-subtitle":
                return []string{"Video upload fails", "Subtitles are missing", "Subtitles are inaccurate", "Processing fails", "Other error"}
        case "video-to-gif":
                return []string{"Upload fails", "GIF conversion fails", "GIF is too large", "Output is missing", "Other error"}
        case "video-to-reels":
                return []string{"Upload fails", "Conversion fails", "Aspect ratio is incorrect", "Output is missing", "Other error"}
        case "gateway":
                return []string{"Website is unavailable", "HTTP 404 or 500 error", "Microservice is unreachable", "Slow response", "Other error"}
        case "payment":
                return []string{"Payment failed", "Payment is pending", "Amount was deducted", "Payment status is incorrect", "Other error"}
        case "user-service":
                return []string{"Login fails", "Registration fails", "Password reset fails", "Account or database error", "Other error"}
        default:
                return []string{"Upload fails", "Processing fails", "Other error"}
        }
}

func environmentQuestion(service string) string {
        switch service {
        case "gateway":
                return "Where are you seeing the gateway problem?"
        case "payment":
                return "At which stage does the payment problem occur?"
        case "user-service":
                return "At which stage does the account problem occur?"
        default:
                return "At which stage does the problem occur?"
        }
}

func environmentOptions(service string) []string {
        switch service {
        case "gateway":
                return []string{"Website does not open", "Page opens but request fails", "Only one microservice fails", "All services fail"}
        case "payment":
                return []string{"Before payment", "During payment", "After payment", "Payment status is unclear"}
        case "user-service":
                return []string{"Before submitting", "After submitting", "Database or server error", "Problem occurs intermittently"}
        default:
                return []string{"During upload", "During processing", "While downloading the result", "Problem occurs intermittently"}
        }
}

func changeQuestion(service string) string {
        switch service {
        case "gateway":
                return "Did anything change recently in gateway configuration, routing, DNS, or deployment?"
        case "payment":
                return "Did anything change recently in payment configuration, the provider, or deployment?"
        case "user-service":
                return "Did anything change recently in authentication, database configuration, or deployment?"
        default:
                return "Did anything change recently, such as the input file, settings, or service deployment?"
        }
}

func impactQuestion(service string) string {
        switch service {
        case "gateway":
                return "How many services are affected?"
        case "payment":
                return "What is the impact of this payment issue?"
        case "user-service":
                return "How many users are affected?"
        default:
                return "Does this happen with every file or only with a particular file?"
        }
}

func scopeOptions(service string) []string {
        switch service {
        case "gateway":
                return []string{"All services", "One service", "One endpoint", "Intermittently"}
        case "payment":
                return []string{"Every transaction", "One transaction", "One payment method", "Intermittently"}
        case "user-service":
                return []string{"All users", "One user", "One operation", "Intermittently"}
        default:
                return []string{"Every file", "One file", "Large files only", "Intermittently"}
        }
}

func troubleshooting(s Session) string {
        issue := normalize(s.Issue)
        errorText := normalize(s.ErrorMessage)
        env := normalize(s.Environment)
        changes := normalize(s.RecentChanges)
        scope := normalize(s.Scope)

        advice := []string{}

        add := func(value string) {
                advice = append(advice, value)
        }

        switch s.Service {
        case "audio-cutter":
                add("Confirm the audio format is supported and the file plays correctly.")
                add("Verify that the start time is before the end time and both are within the audio duration.")
                add("Test with a short audio file.")
        case "audio-joiner":
                add("Confirm all audio files are supported, readable, and fully uploaded.")
                add("Try joining two short files first.")
                add("Check compatibility of audio formats, sample rates, and channels.")
        case "audio-to-video":
                add("Confirm the audio file is readable and the output settings are valid.")
                add("Verify that any required background image is supported and uploaded.")
                add("Test with a short audio file and a small image.")
        case "image-compressor":
                add("Confirm the image format is supported and the image opens correctly.")
                add("Test with a smaller image and check compression settings.")
                add("Compare input and output dimensions and file sizes.")
        case "image-to-pdf":
                add("Confirm all images are supported, readable, and fully uploaded.")
                add("Try converting one image before processing multiple images.")
                add("Check page size, image ordering, and layout.")
        case "pdf-to-jpg":
                add("Confirm the PDF opens correctly and is not password-protected.")
                add("Test with a small PDF containing one or two pages.")
                add("Check whether conversion fails on all pages or only specific pages.")
        case "pdf-to-word":
                add("Confirm the PDF is readable and not password-protected.")
                add("Test with a small PDF containing selectable text.")
                add("For scanned PDFs, check whether OCR is supported and enabled.")
        case "video-cutter":
                add("Confirm the video format is supported and the file plays correctly.")
                add("Check that the start time precedes the end time and both are within the video duration.")
                add("Test with a short clip and verify FFmpeg availability if processing fails.")
        case "video-subtitle":
                add("Confirm the video has an audio track if speech transcription is required.")
                add("Check the selected subtitle language and transcription settings.")
                add("Test with a short clip containing clear speech.")
        case "video-to-gif":
                add("Confirm the video format is supported and the input is readable.")
                add("Test a short clip at lower resolution and frame rate.")
                add("Check the start time, duration, output size, and FFmpeg availability.")
        case "video-to-reels":
                add("Confirm the input video is supported and within configured duration limits.")
                add("Check aspect ratio, cropping, resolution, and output settings.")
                add("Test with a short clip.")
        case "word-to-pdf":
                add("Confirm the document is a valid, readable DOCX file.")
                add("Test with a small document and check the conversion software installation.")
                add("If formatting differs, inspect fonts, page breaks, and layout settings.")
        case "gateway":
                add("Check gateway logs for request path, upstream URL, HTTP status, and connection errors.")
                add("Verify that the affected service is running and reachable from the gateway.")
                add("Check service URLs, routing paths, DNS, and upstream timeouts.")
        case "payment":
                add("Check payment service logs and the provider response for the affected transaction.")
                add("Verify provider connectivity and configuration without exposing credentials.")
                add("If money was deducted or status is uncertain, verify the transaction before retrying.")
        case "user-service":
                add("Check logs for authentication, registration, validation, or database errors.")
                add("Verify database connectivity and dependent authentication services.")
                add("Inspect the failing browser Network request and its HTTP status.")
        }

        switch {
        case strings.Contains(issue, "upload") || strings.Contains(errorText, "upload"):
                add("Check upload failures, file-size limits, supported file types, permissions, and disk space.")
        case strings.Contains(issue, "timeout") || strings.Contains(errorText, "timeout") || strings.Contains(errorText, "deadline"):
                add("Check request timeouts, processing duration, resource usage, and connectivity between services.")
        case strings.Contains(errorText, "404") || strings.Contains(errorText, "not found"):
                add("Verify the requested path, output location, response status, and whether the expected output was generated.")
        case strings.Contains(issue, "failed") || strings.Contains(issue, "error") || strings.Contains(errorText, "500") || strings.Contains(errorText, "internal server error"):
                add("Record the exact error and timestamp, then correlate them with service logs and the failing request.")
        case strings.Contains(issue, "quality") || strings.Contains(issue, "format") || strings.Contains(issue, "aspect"):
                add("Compare input and output properties and verify format, quality, and conversion settings.")
        }

        if strings.Contains(errorText, "permission denied") || strings.Contains(errorText, "forbidden") || strings.Contains(errorText, "403") {
                add("Check access permissions, authentication, and authorization.")
        }

        if strings.Contains(errorText, "connection refused") || strings.Contains(errorText, "connection reset") || strings.Contains(errorText, "no such host") {
                add("Check service availability, hostnames, ports, DNS, and network connectivity.")
        }

        if strings.Contains(errorText, "out of memory") || strings.Contains(errorText, "no space left") {
                add("Check available memory, disk capacity, temporary storage, and container resource limits.")
        }

        if strings.Contains(scope, "large") {
                add("Compare a failing large input with a smaller working input and review processing limits.")
        }

        if strings.Contains(scope, "intermittently") {
                add("Record timestamps for successful and failed requests; check resource saturation, restarts, and dependency availability.")
        }

        if strings.Contains(scope, "all") || strings.Contains(scope, "every") {
                add("Because multiple requests are affected, prioritize service health, dependencies, configuration, and recent deployments.")
        }

        if changes != "" && changes != "no" && changes != "none" &&
                !strings.Contains(changes, "no recent") &&
                !strings.Contains(changes, "nothing changed") &&
                !strings.Contains(changes, "not sure") {
                add("Compare recent deployment or configuration changes with the last known working state. Roll back only if the cause is confirmed and rollback is safe.")
        }

        if strings.Contains(env, "download") {
                add("Check response headers, output location, file permissions, and whether the generated file exists.")
        }

        var result strings.Builder
        result.WriteString("Troubleshooting summary for ")
        result.WriteString(serviceNames[s.Service])
        result.WriteString("\n\nReported issue: ")
        result.WriteString(s.Issue)
        result.WriteString("\nFailure stage: ")
        result.WriteString(s.Environment)
        result.WriteString("\nRecent changes: ")
        result.WriteString(s.RecentChanges)
        result.WriteString("\nAffected scope: ")
        result.WriteString(s.Scope)

        if s.ErrorMessage != "" {
                result.WriteString("\nError details: ")
                result.WriteString(s.ErrorMessage)
        }

        result.WriteString("\n\nRecommended checks:\n- ")
        result.WriteString(strings.Join(advice, "\n- "))
        result.WriteString("\n\nThese recommendations are based on your answers and do not confirm a root cause.")

        return result.String()
}

func closeConversation(session *Session, conn *websocket.Conn, message string) {
        if err := sendText(conn, message); err != nil {
                log.Printf("Could not send closing message: %v", err)
        }

        session.Stage = "closed"
        log.Println("Conversation closed.")
}

func ws(w http.ResponseWriter, r *http.Request) {
        conn, err := upgrader.Upgrade(w, r, nil)
        if err != nil {
                log.Printf("WebSocket upgrade failed: %v", err)
                return
        }
        defer conn.Close()

        session := Session{
                Stage: "describe_problem",
        }

        if err := sendText(conn, "Hi, I'm Alina. Welcome to Chat Desk, how may I help you?"); err != nil {
                return
        }

        for {
                _, raw, err := conn.ReadMessage()
                if err != nil {
                        return
                }

                if session.Stage == "closed" {
                        return
                }

                text := receiveText(raw)
                query := normalize(text)

                if query == "" {
                        if err := sendText(conn, "Please enter a response so I can continue troubleshooting."); err != nil {
                                return
                        }
                        continue
                }

                switch session.Stage {
                case "describe_problem":
                        session.Issue = text
                        session.Stage = "choose_service"

                        if err := sendServices(conn, "Thanks for explaining the issue. Which microservice would you like help with?"); err != nil {
                                return
                        }

                case "choose_service":
                        service := findService(text)
                        if service == "" {
                                if err := sendServices(conn, "I have your issue description. Please select the microservice affected by the problem."); err != nil {
                                        return
                                }
                                continue
                        }

                        session.Service = service
                        session.Stage = "describe_issue"

                        if err := sendOptions(conn, questionForService(service), issueOptions(service)); err != nil {
                                return
                        }

                case "describe_issue":
                        session.Issue = text
                        session.Stage = "environment"

                        if err := sendOptions(conn, environmentQuestion(session.Service), environmentOptions(session.Service)); err != nil {
                                return
                        }

                case "environment":
                        session.Environment = text
                        session.Stage = "error_details"

                        if err := sendText(conn, "Please provide the exact error message or HTTP status code, if available. If there is no error message, type \"none\"."); err != nil {
                                return
                        }

                case "error_details":
                        if query != "none" && query != "no error" && query != "not available" {
                                session.ErrorMessage = text
                        }

                        session.Stage = "recent_changes"

                        if err := sendOptions(conn, changeQuestion(session.Service), []string{
                                "Yes, something changed",
                                "No recent changes",
                                "Not sure",
                        }); err != nil {
                                return
                        }

                case "recent_changes":
                        session.RecentChanges = text
                        session.Stage = "scope"

                        if err := sendOptions(conn, impactQuestion(session.Service), scopeOptions(session.Service)); err != nil {
                                return
                        }

                case "scope":
                        session.Scope = text
                        session.Stage = "resolution"

                        if err := sendText(conn, troubleshooting(session)); err != nil {
                                return
                        }

                        if err := sendOptions(conn,
                                "Is the issue resolved after checking these recommendations?",
                                []string{"Yes, resolved", "No, still happening"},
                        ); err != nil {
                                return
                        }

                case "resolution":
                        if isYes(query) {
                                session.Stage = "another_service"

                                if err := sendOptions(conn,
                                        "Thank you! Is there any other service you would like recommendations or help with?",
                                        []string{"Yes", "No"},
                                ); err != nil {
                                        return
                                }
                                continue
                        }

                        if isNo(query) {
                                closeConversation(
                                        &session,
                                        conn,
                                        "The issue is still unresolved. Please reach out to support via email at manohar@gmail.com or call 79776512305. Thank you for contacting Chat Desk. Goodbye!",
                                )
                                return
                        }

                        if err := sendOptions(conn,
                                "Please confirm whether the issue is resolved.",
                                []string{"Yes, resolved", "No, still happening"},
                        ); err != nil {
                                return
                        }

                case "another_service":
                        if isYes(query) {
                                issue := session.Issue
                                session = Session{
                                        Stage: "choose_service",
                                        Issue: issue,
                                }

                                if err := sendServices(conn, "Which microservice would you like help with?"); err != nil {
                                        return
                                }
                                continue
                        }

                        if isNo(query) {
                                closeConversation(
                                        &session,
                                        conn,
                                        "Thank you for using Media Tools Support. Thank you for your time. Goodbye!",
                                )
                                return
                        }

                        if err := sendOptions(conn,
                                "Would you like help with another service? Please select Yes or No.",
                                []string{"Yes", "No"},
                        ); err != nil {
                                return
                        }
                }
        }
}

