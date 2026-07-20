package com.heoclub.aitravel.navigation

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.heoclub.aitravel.AiTravelApplication
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.repository.AddPlaceResult
import com.heoclub.aitravel.ui.components.AddPlaceToPlanDialog
import com.heoclub.aitravel.ui.assistant.AiAssistantScreen
import com.heoclub.aitravel.ui.assistant.AiAssistantViewModel
import com.heoclub.aitravel.ui.createplan.AiPlanDraftInput
import com.heoclub.aitravel.data.model.AiHotelStayInput
import com.heoclub.aitravel.data.model.AiMapPointInput
import com.heoclub.aitravel.ui.createplan.AiPlanGenerationScreen
import com.heoclub.aitravel.ui.createplan.AiPlanGenerationViewModel
import com.heoclub.aitravel.ui.createplan.CreatePlanScreen
import com.heoclub.aitravel.ui.createplan.CreatePlanViewModel
import com.heoclub.aitravel.ui.detail.PlanDetailScreen
import com.heoclub.aitravel.ui.detail.PlanDetailViewModel
import com.heoclub.aitravel.ui.discover.DiscoverScreen
import com.heoclub.aitravel.ui.explore.ExploreViewModel
import com.heoclub.aitravel.ui.explore.rememberExploreMapViewHolder
import com.heoclub.aitravel.ui.home.HomeViewModel
import com.heoclub.aitravel.ui.journey.JourneyJournalEditorScreen
import com.heoclub.aitravel.ui.journey.JourneyJournalDetailScreen
import com.heoclub.aitravel.ui.journey.JourneyJournalScreen
import com.heoclub.aitravel.ui.journey.JourneyScreen
import com.heoclub.aitravel.ui.journey.seedJournalEntries
import com.heoclub.aitravel.ui.plan.PlanHomeScreen
import com.heoclub.aitravel.ui.plan.PlanHomeViewModel
import com.heoclub.aitravel.ui.place.PlaceDetailScreen
import com.heoclub.aitravel.ui.place.PlaceDetailViewModel
import com.heoclub.aitravel.ui.profile.ProfileScreen

private object Routes {
    const val createPlan = "create-plan"
    const val journeyJournal = "journey-journal"
    const val journeyJournalEditor = "journey-journal-editor"
    const val journeyJournalDetailPattern = "journey-journal-detail/{entryId}"
    const val planDetailPattern = "plan-detail/{planId}"
    const val placeDetailPattern = "place-detail/{placeId}"
    const val assistantPattern = "assistant?question={question}&planId={planId}"
    const val aiPlanGenerationPattern =
        "ai-plan-generation?destination={destination}&dateRange={dateRange}&dayCount={dayCount}" +
            "&preferences={preferences}&freeText={freeText}&pace={pace}&transport={transport}" +
            "&dailyStart={dailyStart}&dailyEnd={dailyEnd}&arrivalStation={arrivalStation}&arrivalDay={arrivalDay}&arrivalTime={arrivalTime}" +
            "&departureStation={departureStation}&departureDay={departureDay}&departureTime={departureTime}&hotelName={hotelName}" +
            "&hotelStays={hotelStays}&mapPoints={mapPoints}&optimizationMode={optimizationMode}"

    fun planDetail(planId: String): String = "plan-detail/$planId"
    fun placeDetail(placeId: String): String = "place-detail/$placeId"
    fun journeyJournalDetail(entryId: String): String = "journey-journal-detail/${Uri.encode(entryId)}"

    fun aiPlanGeneration(
        destination: String,
        dateRange: String,
        dayCount: Int,
        preferences: List<String>,
        freeText: String?,
        pace: String,
        transportPreference: String,
        dailyStart: String,
        dailyEnd: String,
        arrivalStation: String?,
        arrivalPoint: AiMapPointInput?,
        arrivalDay: Int,
        arrivalTime: String?,
        departureStation: String?,
        departurePoint: AiMapPointInput?,
        departureDay: Int?,
        departureTime: String?,
        hotelName: String?,
        hotelPoint: AiMapPointInput?,
        hotelStays: List<AiHotelStayInput>,
        optimizationMode: String,
    ): String {
        return "ai-plan-generation" +
            "?destination=${Uri.encode(destination)}" +
            "&dateRange=${Uri.encode(dateRange)}" +
            "&dayCount=$dayCount" +
            "&preferences=${Uri.encode(preferences.joinToString("|"))}" +
            "&freeText=${Uri.encode(freeText.orEmpty())}" +
            "&pace=${Uri.encode(pace)}" +
            "&transport=${Uri.encode(transportPreference)}" +
            "&dailyStart=${Uri.encode(dailyStart)}" +
            "&dailyEnd=${Uri.encode(dailyEnd)}" +
            "&arrivalStation=${Uri.encode(arrivalStation.orEmpty())}" +
            "&arrivalDay=$arrivalDay" +
            "&arrivalTime=${Uri.encode(arrivalTime.orEmpty())}" +
            "&departureStation=${Uri.encode(departureStation.orEmpty())}" +
            "&departureDay=${departureDay ?: dayCount}" +
            "&departureTime=${Uri.encode(departureTime.orEmpty())}" +
            "&hotelName=${Uri.encode(hotelName.orEmpty())}" +
            "&hotelStays=${Uri.encode(hotelStays.joinToString(";;") { stay -> encodeHotelStay(stay) })}" +
            "&mapPoints=${Uri.encode(encodeMapPoints(arrivalPoint, departurePoint, hotelPoint))}" +
            "&optimizationMode=${Uri.encode(optimizationMode)}"
    }

    fun assistant(
        question: String? = null,
        planId: String? = null,
    ): String {
        val query = buildList {
            if (!question.isNullOrBlank()) add("question=${Uri.encode(question)}")
            if (!planId.isNullOrBlank()) add("planId=${Uri.encode(planId)}")
        }.joinToString("&")
        return if (query.isBlank()) "assistant" else "assistant?$query"
    }
}

private fun encodeHotelStay(stay: AiHotelStayInput): String {
    val point = stay.mapPoint
    return listOf(
        stay.checkInDay,
        stay.checkOutDay,
        point?.latitude ?: "",
        point?.longitude ?: "",
        stay.name.replace(',', '，').replace(";;", "；；"),
        point?.address.orEmpty().replace(',', '，').replace(";;", "；；"),
    ).joinToString(",")
}

private fun encodeMapPoints(
    arrival: AiMapPointInput?,
    departure: AiMapPointInput?,
    hotel: AiMapPointInput?,
): String {
    return listOf("arrival" to arrival, "departure" to departure, "hotel" to hotel)
        .mapNotNull { (key, point) ->
            point?.let {
                listOf(
                    key,
                    it.latitude,
                    it.longitude,
                    it.name.replace(',', '，').replace(";;", "；；"),
                    it.address.orEmpty().replace(',', '，').replace(";;", "；；"),
                ).joinToString(",")
            }
        }
        .joinToString(";;")
}

private fun decodeMapPoints(value: String): Map<String, AiMapPointInput> {
    return value.split(";;").mapNotNull { encoded ->
        val parts = encoded.split(',', limit = 5)
        val key = parts.getOrNull(0)?.takeIf { it in setOf("arrival", "departure", "hotel") }
        val latitude = parts.getOrNull(1)?.toDoubleOrNull()
        val longitude = parts.getOrNull(2)?.toDoubleOrNull()
        val name = parts.getOrNull(3)?.trim().orEmpty()
        if (key != null && latitude != null && longitude != null && name.isNotBlank()) {
            key to AiMapPointInput(
                name = name,
                address = parts.getOrNull(4)?.trim()?.takeIf(String::isNotBlank),
                latitude = latitude,
                longitude = longitude,
            )
        } else null
    }.toMap()
}

private data class ExplorePlanContext(
    val planId: String,
    val destination: String,
    val requestKey: Long,
)

@Composable
fun AiTravelNavHost() {
    val navController = rememberNavController()
    val application = LocalContext.current.applicationContext as AiTravelApplication
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = navBackStackEntry?.destination
    val currentRoute = currentDestination?.route
    val mainDestinations = AppDestination.entries
    val showPrimaryChrome = currentRoute in mainDestinations.map { it.route }
    val travelPlans by application.container.travelPlanRepository.plans.collectAsState()
    val currentLocationRepository = application.container.currentLocationRepository
    val currentLocationState by currentLocationRepository.state.collectAsState()
    val exploreMapViewHolder = rememberExploreMapViewHolder()
    var pendingPlaceToAdd by remember { mutableStateOf<PlaceSummary?>(null) }
    var explorePlanContext by remember { mutableStateOf<ExplorePlanContext?>(null) }
    val journalEntries = remember { mutableStateListOf(*seedJournalEntries.toTypedArray()) }
    val locationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { permissions ->
        val granted = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
            permissions[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (granted) {
            currentLocationRepository.refreshLocation()
        } else {
            currentLocationRepository.reportPermissionDenied()
        }
    }
    val requestCurrentLocation: () -> Unit = {
        val hasPermission = ContextCompat.checkSelfPermission(
            application,
            Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(
                application,
                Manifest.permission.ACCESS_COARSE_LOCATION,
            ) == PackageManager.PERMISSION_GRANTED
        if (hasPermission) {
            currentLocationRepository.refreshLocation()
        } else {
            locationPermissionLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                ),
            )
        }
    }

    LaunchedEffect(Unit) {
        requestCurrentLocation()
    }

    Scaffold(
        bottomBar = {
            if (showPrimaryChrome) {
                NavigationBar {
                    mainDestinations.forEach { destination ->
                        val selected = currentDestination?.hierarchy?.any {
                            it.route == destination.route
                        } == true

                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                if (destination != AppDestination.Explore) {
                                    explorePlanContext = null
                                }
                                navController.navigate(destination.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = {
                                Icon(
                                    imageVector = destination.icon,
                                    contentDescription = destination.label,
                                )
                            },
                            label = { Text(destination.label) },
                        )
                    }
                }
            }
        },
        floatingActionButton = {
            if (showPrimaryChrome) {
                FloatingActionButton(
                    onClick = {
                        navController.navigate(Routes.assistant())
                    },
                ) {
                    Icon(
                        imageVector = Icons.Outlined.SmartToy,
                        contentDescription = "AI 旅行助手",
                    )
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = AppDestination.Plan.route,
            modifier = Modifier.padding(innerPadding),
            enterTransition = { EnterTransition.None },
            exitTransition = { ExitTransition.None },
            popEnterTransition = { EnterTransition.None },
            popExitTransition = { ExitTransition.None },
        ) {
            composable(AppDestination.Plan.route) {
                val planHomeViewModel: PlanHomeViewModel = viewModel(
                    factory = PlanHomeViewModel.Factory(application.container.travelPlanRepository),
                )
                PlanHomeScreen(
                    viewModel = planHomeViewModel,
                    locationState = currentLocationState,
                    onLocate = requestCurrentLocation,
                    onCreatePlan = { navController.navigate(Routes.createPlan) },
                    onOpenPlan = { planId -> navController.navigate(Routes.planDetail(planId)) },
                    onAskAi = { question -> navController.navigate(Routes.assistant(question = question)) },
                )
            }
            composable(AppDestination.Explore.route) {
                val exploreViewModel: ExploreViewModel = viewModel(
                    factory = ExploreViewModel.Factory(application.container.exploreRepository),
                )
                DiscoverScreen(
                    viewModel = exploreViewModel,
                    mapViewHolder = exploreMapViewHolder,
                    locationState = currentLocationState,
                    requestedDestination = explorePlanContext?.destination,
                    destinationRequestKey = explorePlanContext?.requestKey,
                    onLocate = {
                        explorePlanContext = null
                        requestCurrentLocation()
                    },
                    onOpenPlace = { placeId -> navController.navigate(Routes.placeDetail(placeId)) },
                    onAddPlace = { place -> pendingPlaceToAdd = place },
                )
            }
            composable(AppDestination.Journey.route) {
                JourneyScreen(
                    journalEntries = journalEntries,
                    onOpenJournal = { navController.navigate(Routes.journeyJournal) },
                    onOpenJournalEntry = { entryId -> navController.navigate(Routes.journeyJournalDetail(entryId)) },
                )
            }
            composable(AppDestination.Profile.route) {
                val homeViewModel: HomeViewModel = viewModel(
                    factory = HomeViewModel.Factory(application.container.healthRepository),
                )
                ProfileScreen(viewModel = homeViewModel)
            }
            composable(Routes.journeyJournal) {
                JourneyJournalScreen(
                    entries = journalEntries,
                    onBack = { navController.popBackStack() },
                    onWriteJourney = { navController.navigate(Routes.journeyJournalEditor) },
                    onAddEntry = { entry -> journalEntries.add(0, entry) },
                    onOpenEntry = { entryId -> navController.navigate(Routes.journeyJournalDetail(entryId)) },
                )
            }
            composable(Routes.journeyJournalEditor) {
                JourneyJournalEditorScreen(
                    onBack = { navController.popBackStack() },
                    onSave = { entry ->
                        journalEntries.add(0, entry)
                        navController.popBackStack()
                    },
                )
            }
            composable(
                route = Routes.journeyJournalDetailPattern,
                arguments = listOf(navArgument("entryId") { type = NavType.StringType }),
            ) { backStackEntry ->
                val entryId = backStackEntry.arguments?.getString("entryId").orEmpty()
                val entry = journalEntries.firstOrNull { it.id == entryId }
                if (entry != null) {
                    JourneyJournalDetailScreen(
                        entry = entry,
                        onBack = { navController.popBackStack() },
                    )
                }
            }
            composable(Routes.createPlan) {
                val createPlanViewModel: CreatePlanViewModel = viewModel(
                    factory = CreatePlanViewModel.Factory(
                        application.container.travelPlanRepository,
                        application.container.exploreRepository,
                    ),
                )
                CreatePlanScreen(
                    viewModel = createPlanViewModel,
                    onBack = { navController.popBackStack() },
                    onDone = { navController.popBackStack() },
                    onStartAiPlanning = { input ->
                        navController.navigate(
                            Routes.aiPlanGeneration(
                                destination = input.destination,
                                dateRange = input.dateRange,
                                dayCount = input.dayCount,
                                preferences = input.preferences,
                                freeText = input.freeText,
                                pace = input.pace,
                                transportPreference = input.transportPreference,
                                dailyStart = input.dailyStart,
                                dailyEnd = input.dailyEnd,
                                arrivalStation = input.arrivalStation,
                                arrivalPoint = input.arrivalPoint,
                                arrivalDay = input.arrivalDay,
                                arrivalTime = input.arrivalTime,
                                departureStation = input.departureStation,
                                departurePoint = input.departurePoint,
                                departureDay = input.departureDay,
                                departureTime = input.departureTime,
                                hotelName = input.hotelName,
                                hotelPoint = input.hotelPoint,
                                hotelStays = input.hotelStays,
                                optimizationMode = input.optimizationMode,
                            ),
                        )
                    },
                )
            }
            composable(
                route = Routes.aiPlanGenerationPattern,
                arguments = listOf(
                    navArgument("destination") { type = NavType.StringType },
                    navArgument("dateRange") { type = NavType.StringType },
                    navArgument("dayCount") { type = NavType.IntType },
                    navArgument("preferences") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("freeText") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("pace") {
                        type = NavType.StringType
                        defaultValue = "BALANCED"
                    },
                    navArgument("transport") {
                        type = NavType.StringType
                        defaultValue = "MIXED"
                    },
                    navArgument("dailyStart") {
                        type = NavType.StringType
                        defaultValue = "09:00"
                    },
                    navArgument("dailyEnd") {
                        type = NavType.StringType
                        defaultValue = "20:00"
                    },
                    navArgument("arrivalStation") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("arrivalDay") {
                        type = NavType.IntType
                        defaultValue = 1
                    },
                    navArgument("arrivalTime") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("departureStation") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("departureDay") {
                        type = NavType.IntType
                        defaultValue = 1
                    },
                    navArgument("departureTime") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("hotelName") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("hotelStays") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("mapPoints") {
                        type = NavType.StringType
                        defaultValue = ""
                    },
                    navArgument("optimizationMode") {
                        type = NavType.StringType
                        defaultValue = "REQUIRED"
                    },
                ),
            ) { backStackEntry ->
                val mapPoints = decodeMapPoints(backStackEntry.arguments?.getString("mapPoints").orEmpty())
                val input = AiPlanDraftInput(
                    destination = backStackEntry.arguments?.getString("destination").orEmpty(),
                    dateRange = backStackEntry.arguments?.getString("dateRange").orEmpty(),
                    dayCount = backStackEntry.arguments?.getInt("dayCount") ?: 1,
                    preferences = backStackEntry.arguments?.getString("preferences")
                        .orEmpty()
                        .split('|')
                        .filter(String::isNotBlank),
                    freeText = backStackEntry.arguments?.getString("freeText")
                        ?.takeIf(String::isNotBlank),
                    pace = backStackEntry.arguments?.getString("pace") ?: "BALANCED",
                    transportPreference = backStackEntry.arguments?.getString("transport") ?: "MIXED",
                    dailyStart = backStackEntry.arguments?.getString("dailyStart") ?: "09:00",
                    dailyEnd = backStackEntry.arguments?.getString("dailyEnd") ?: "20:00",
                    arrivalStation = backStackEntry.arguments?.getString("arrivalStation")?.takeIf(String::isNotBlank),
                    arrivalPoint = mapPoints["arrival"],
                    arrivalDay = backStackEntry.arguments?.getInt("arrivalDay") ?: 1,
                    arrivalTime = backStackEntry.arguments?.getString("arrivalTime")?.takeIf(String::isNotBlank),
                    departureStation = backStackEntry.arguments?.getString("departureStation")?.takeIf(String::isNotBlank),
                    departurePoint = mapPoints["departure"],
                    departureDay = backStackEntry.arguments?.getInt("departureDay"),
                    departureTime = backStackEntry.arguments?.getString("departureTime")?.takeIf(String::isNotBlank),
                    hotelName = backStackEntry.arguments?.getString("hotelName")?.takeIf(String::isNotBlank),
                    hotelPoint = mapPoints["hotel"],
                    hotelStays = backStackEntry.arguments?.getString("hotelStays")
                        .orEmpty()
                        .split(";;")
                        .mapNotNull { encoded ->
                            val parts = encoded.split(',', limit = 6)
                            val checkIn = parts.getOrNull(0)?.toIntOrNull()
                            val checkOut = parts.getOrNull(1)?.toIntOrNull()
                            val latitude = parts.getOrNull(2)?.toDoubleOrNull()
                            val longitude = parts.getOrNull(3)?.toDoubleOrNull()
                            val name = parts.getOrNull(4)?.trim().orEmpty()
                            val address = parts.getOrNull(5)?.trim()?.takeIf(String::isNotBlank)
                            if (checkIn != null && checkOut != null && name.isNotBlank()) {
                                AiHotelStayInput(
                                    name,
                                    checkIn,
                                    checkOut,
                                    if (latitude != null && longitude != null) {
                                        AiMapPointInput(name, address, latitude, longitude)
                                    } else null,
                                )
                            } else null
                        },
                    optimizationMode = backStackEntry.arguments?.getString("optimizationMode") ?: "REQUIRED",
                )
                val generationViewModel: AiPlanGenerationViewModel = viewModel(
                    factory = AiPlanGenerationViewModel.Factory(
                        input = input,
                        aiRepository = application.container.aiRepository,
                        travelPlanRepository = application.container.travelPlanRepository,
                        exploreRepository = application.container.exploreRepository,
                    ),
                )
                AiPlanGenerationScreen(
                    viewModel = generationViewModel,
                    onBack = { navController.popBackStack() },
                    onOpenPlan = { planId ->
                        navController.navigate(Routes.planDetail(planId)) {
                            popUpTo(Routes.createPlan) { inclusive = true }
                        }
                    },
                    onOpenPlace = { placeId -> navController.navigate(Routes.placeDetail(placeId)) },
                )
            }
            composable(
                route = Routes.planDetailPattern,
                arguments = listOf(navArgument("planId") { type = NavType.StringType }),
            ) { backStackEntry ->
                val planId = backStackEntry.arguments?.getString("planId").orEmpty()
                val detailViewModel: PlanDetailViewModel = viewModel(
                    factory = PlanDetailViewModel.Factory(
                        planId = planId,
                        travelPlanRepository = application.container.travelPlanRepository,
                        routeRepository = application.container.routeRepository,
                    ),
                )
                PlanDetailScreen(
                    viewModel = detailViewModel,
                    onBack = { navController.popBackStack() },
                    onAskAi = { id -> navController.navigate(Routes.assistant(planId = id)) },
                    onContinueAdding = { id, destination ->
                        explorePlanContext = ExplorePlanContext(
                            planId = id,
                            destination = destination,
                            requestKey = System.nanoTime(),
                        )
                        navController.navigate(AppDestination.Explore.route) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    onOpenPlace = { item ->
                        val place = item.toPlaceSummary()
                        application.container.exploreRepository.upsertPlace(place)
                        navController.navigate(Routes.placeDetail(place.id))
                    },
                )
            }
            composable(
                route = Routes.placeDetailPattern,
                arguments = listOf(navArgument("placeId") { type = NavType.StringType }),
            ) { backStackEntry ->
                val placeId = backStackEntry.arguments?.getString("placeId").orEmpty()
                val placeDetailViewModel: PlaceDetailViewModel = viewModel(
                    factory = PlaceDetailViewModel.Factory(
                        placeId = placeId,
                        exploreRepository = application.container.exploreRepository,
                    ),
                )
                val travelPlans by application.container.travelPlanRepository.plans.collectAsState()
                PlaceDetailScreen(
                    viewModel = placeDetailViewModel,
                    travelPlans = travelPlans,
                    onBack = { navController.popBackStack() },
                    onCreatePlan = { navController.navigate(Routes.createPlan) },
                    onAddToPlan = { plan, target ->
                        val place = application.container.exploreRepository.getPlace(placeId)
                        if (place == null) {
                            AddPlaceResult.MISSING_LOCATION
                        } else {
                            application.container.travelPlanRepository.addPlaceToPlan(
                                planId = plan.id,
                                place = place,
                                target = target,
                            )
                        }
                    },
                )
            }
            composable(
                route = Routes.assistantPattern,
                arguments = listOf(
                    navArgument("question") {
                        type = NavType.StringType
                        nullable = true
                        defaultValue = null
                    },
                    navArgument("planId") {
                        type = NavType.StringType
                        nullable = true
                        defaultValue = null
                    },
                ),
            ) { backStackEntry ->
                val question = backStackEntry.arguments?.getString("question")
                val planId = backStackEntry.arguments?.getString("planId")
                val assistantViewModel: AiAssistantViewModel = viewModel(
                    factory = AiAssistantViewModel.Factory(
                        initialQuestion = question,
                        planId = planId,
                        travelPlanRepository = application.container.travelPlanRepository,
                        aiRepository = application.container.aiRepository,
                    ),
                )
                AiAssistantScreen(
                    viewModel = assistantViewModel,
                    onClose = { navController.popBackStack() },
                )
            }
        }
    }

    pendingPlaceToAdd?.let { place ->
        AddPlaceToPlanDialog(
            plans = travelPlans,
            placeName = place.name,
            initialPlanId = explorePlanContext?.planId,
            onDismiss = { pendingPlaceToAdd = null },
            onCreatePlan = { navController.navigate(Routes.createPlan) },
            onConfirm = { plan, target ->
                application.container.travelPlanRepository.addPlaceToPlan(
                    planId = plan.id,
                    place = place,
                    target = target,
                )
            },
            onResult = { message ->
                Toast.makeText(application, message, Toast.LENGTH_SHORT).show()
            },
        )
    }
}

private fun PlanItem.toPlaceSummary(): PlaceSummary {
    return PlaceSummary(
        id = id,
        source = source,
        sourcePoiId = sourcePoiId,
        name = name,
        category = category,
        categoryCode = categoryCode,
        typeName = typeName,
        typeCode = typeCode,
        address = address,
        provinceName = provinceName,
        cityName = cityName,
        districtName = districtName,
        adCode = adCode,
        cityCode = cityCode,
        latitude = latitude,
        longitude = longitude,
        phone = phone,
        rating = rating,
        costAverage = costAverage,
        coverImageUrl = thumbnailUrl,
        imageUrls = imageUrls,
        businessArea = businessArea,
        openingHoursToday = openingHoursToday,
        openingHoursWeek = openingHoursWeek,
    )
}
