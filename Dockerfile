FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN cp input/research_profile.example.md input/research_profile.md && mkdir -p /data && python agent.py init
ENV PORT=8765 NO_BROWSER=1 DATABASE_PATH=/data/faculty.sqlite
EXPOSE 8765
CMD ["python","agent.py","service"]
