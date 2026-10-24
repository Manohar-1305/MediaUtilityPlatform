FROM golang:1.23-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o micro-bot .

FROM alpine:3.21

WORKDIR /app

COPY --from=builder /app/micro-bot .
COPY --from=builder /app/static ./static

EXPOSE 5017

CMD ["./micro-bot"]
