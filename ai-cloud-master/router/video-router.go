package router

import (
	"github.com/QuantumNous/new-api/controller"
	"github.com/QuantumNous/new-api/middleware"

	"github.com/gin-gonic/gin"
)

func SetVideoRouter(router *gin.Engine) {
	videoV1Router := router.Group("/v1")
	// Tag video generation routes independently from generic web requests in access logs.
	videoV1Router.Use(middleware.RouteTag("video"))
	videoV1Router.Use(middleware.RequestParamLogger())
	videoV1Router.Use(middleware.TokenAuth(), middleware.Distribute())
	{
		videoV1Router.GET("/videos/:task_id/content", controller.VideoProxy)
		videoV1Router.POST("/video/generations", controller.RelayTask)
		videoV1Router.GET("/video/generations/:task_id", controller.RelayTask)
		videoV1Router.POST("/videos/:video_id/remix", controller.RelayTask)
	}
	// openai compatible API video routes
	// docs: https://platform.openai.com/docs/api-reference/videos/create
	{
		videoV1Router.POST("/videos", controller.RelayTask)
		videoV1Router.GET("/videos/:task_id", controller.RelayTask)
	}

	klingV1Router := router.Group("/kling/v1")
	// Tag Kling video relay routes with the same video family for consistent logs.
	klingV1Router.Use(middleware.RouteTag("video"))
	klingV1Router.Use(middleware.RequestParamLogger())
	klingV1Router.Use(middleware.KlingRequestConvert(), middleware.TokenAuth(), middleware.Distribute())
	{
		klingV1Router.POST("/videos/text2video", controller.RelayTask)
		klingV1Router.POST("/videos/image2video", controller.RelayTask)
		klingV1Router.GET("/videos/text2video/:task_id", controller.RelayTask)
		klingV1Router.GET("/videos/image2video/:task_id", controller.RelayTask)
	}

	// Jimeng official API routes - direct mapping to official API format
	jimengOfficialGroup := router.Group("jimeng")
	// Tag Jimeng official video relay routes with the video family as well.
	jimengOfficialGroup.Use(middleware.RouteTag("video"))
	jimengOfficialGroup.Use(middleware.RequestParamLogger())
	jimengOfficialGroup.Use(middleware.JimengRequestConvert(), middleware.TokenAuth(), middleware.Distribute())
	{
		// Maps to: /?Action=CVSync2AsyncSubmitTask&Version=2022-08-31 and /?Action=CVSync2AsyncGetResult&Version=2022-08-31
		jimengOfficialGroup.POST("/", controller.RelayTask)
	}
}
