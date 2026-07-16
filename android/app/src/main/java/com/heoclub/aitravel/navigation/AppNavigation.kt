package com.heoclub.aitravel.navigation

import android.net.Uri
import android.widget.Toast
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
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
import com.heoclub.aitravel.data.repository.AddPlaceResult
import com.heoclub.aitravel.ui.components.AddPlaceToPlanDialog
import com.heoclub.aitravel.ui.assistant.AiAssistantScreen
import com.heoclub.aitravel.ui.assistant.AiAssistantViewModel
import com.heoclub.aitravel.ui.createplan.CreatePlanScreen
import com.heoclub.aitravel.ui.createplan.CreatePlanViewModel
import com.heoclub.aitravel.ui.detail.PlanDetailScreen
import com.heoclub.aitravel.ui.detail.PlanDetailViewModel
import com.heoclub.aitravel.ui.discover.DiscoverScreen
import com.heoclub.aitravel.ui.explore.ExploreViewModel
import com.heoclub.aitravel.ui.home.HomeViewModel
import com.heoclub.aitravel.ui.plan.PlanHomeScreen
import com.heoclub.aitravel.ui.plan.PlanHomeViewModel
import com.heoclub.aitravel.ui.place.PlaceDetailScreen
import com.heoclub.aitravel.ui.place.PlaceDetailViewModel
import com.heoclub.aitravel.ui.profile.ProfileScreen

private object Routes {
    const val createPlan = "create-plan"
    const val planDetailPattern = "plan-detail/{planId}"
    const val placeDetailPattern = "place-detail/{placeId}"
    const val assistantPattern = "assistant?question={question}&planId={planId}"

    fun planDetail(planId: String): String = "plan-detail/$planId"
    fun placeDetail(placeId: String): String = "place-detail/$placeId"

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
    var pendingPlaceToAdd by remember { mutableStateOf<PlaceSummary?>(null) }

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
        ) {
            composable(AppDestination.Plan.route) {
                val planHomeViewModel: PlanHomeViewModel = viewModel(
                    factory = PlanHomeViewModel.Factory(application.container.travelPlanRepository),
                )
                PlanHomeScreen(
                    viewModel = planHomeViewModel,
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
                    onOpenPlace = { placeId -> navController.navigate(Routes.placeDetail(placeId)) },
                    onAddPlace = { place -> pendingPlaceToAdd = place },
                )
            }
            composable(AppDestination.Profile.route) {
                val homeViewModel: HomeViewModel = viewModel(
                    factory = HomeViewModel.Factory(application.container.healthRepository),
                )
                ProfileScreen(viewModel = homeViewModel)
            }
            composable(Routes.createPlan) {
                val createPlanViewModel: CreatePlanViewModel = viewModel(
                    factory = CreatePlanViewModel.Factory(application.container.travelPlanRepository),
                )
                CreatePlanScreen(
                    viewModel = createPlanViewModel,
                    onBack = { navController.popBackStack() },
                    onDone = { navController.popBackStack() },
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
