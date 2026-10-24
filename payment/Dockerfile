FROM golang:1.23-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN go build -o micro-bot .

FROM alpine:3.21

WORKDIR /app

COPY --from=builder /app/micro-bot .

EXPOSE 5017

CMD ["./micro-bot"]
